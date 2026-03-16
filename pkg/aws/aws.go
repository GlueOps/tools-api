package aws

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/iam"
	"github.com/aws/aws-sdk-go-v2/service/organizations"
	orgtypes "github.com/aws/aws-sdk-go-v2/service/organizations/types"
	"github.com/aws/aws-sdk-go-v2/service/sts"
	"github.com/aws/smithy-go"
)

const (
	iamUserName = "dev-deployment-svc-account"
	iamRoleName = "glueops-captain-role"
	iamPolicyARN = "arn:aws:iam::aws:policy/AdministratorAccess"
	stsSessionName = "SubAccountAccess"
	hardcodedRegion = "us-west-2"
)

// httpError implements error with an HTTP status code for Huma error handling (risk H2).
type httpError struct {
	status int
	detail string
}

func (e *httpError) Error() string  { return e.detail }
func (e *httpError) GetStatus() int { return e.status }

func hError(status int, detail string) error {
	return &httpError{status: status, detail: detail}
}

// newAWSConfig creates an AWS config with static credentials from env vars.
func newAWSConfig() (aws.Config, error) {
	accessKey := os.Getenv("AWS_GLUEOPS_ROCKS_ORG_ACCESS_KEY")
	secretKey := os.Getenv("AWS_GLUEOPS_ROCKS_ORG_SECRET_KEY")
	if accessKey == "" || secretKey == "" {
		return aws.Config{}, fmt.Errorf("AWS_GLUEOPS_ROCKS_ORG_ACCESS_KEY and AWS_GLUEOPS_ROCKS_ORG_SECRET_KEY environment variables are required")
	}

	cfg := aws.Config{
		Region:      hardcodedRegion,
		Credentials: credentials.NewStaticCredentialsProvider(accessKey, secretKey, ""),
	}
	return cfg, nil
}

// listOrganizationAccounts returns all accounts in the organization using pagination.
func listOrganizationAccounts(ctx context.Context, client *organizations.Client) ([]orgtypes.Account, error) {
	var allAccounts []orgtypes.Account
	paginator := organizations.NewListAccountsPaginator(client, &organizations.ListAccountsInput{})
	for paginator.HasMorePages() {
		page, err := paginator.NextPage(ctx)
		if err != nil {
			return nil, fmt.Errorf("failed to list organization accounts: %w", err)
		}
		allAccounts = append(allAccounts, page.Accounts...)
	}
	return allAccounts, nil
}

// findAccountByName finds a sub-account by name from a list of accounts.
func findAccountByName(accounts []orgtypes.Account, name string) (*orgtypes.Account, error) {
	for i := range accounts {
		if aws.ToString(accounts[i].Name) == name {
			return &accounts[i], nil
		}
	}
	return nil, hError(http.StatusNotFound, "Account not found.")
}

// CreateAdminCredentialsWithinCaptainAccount orchestrates the full flow:
// list accounts → find by name → assume role → create user → create key → create role → format .env
func CreateAdminCredentialsWithinCaptainAccount(ctx context.Context, awsSubAccountName string) (string, error) {
	cfg, err := newAWSConfig()
	if err != nil {
		return "", err
	}

	orgClient := organizations.NewFromConfig(cfg)
	stsClient := sts.NewFromConfig(cfg)

	// Step 1: Validate this is the root account.
	orgInfo, err := orgClient.DescribeOrganization(ctx, &organizations.DescribeOrganizationInput{})
	if err != nil {
		return "", fmt.Errorf("failed to describe organization: %w", err)
	}
	masterAccountID := aws.ToString(orgInfo.Organization.MasterAccountId)

	callerIdentity, err := stsClient.GetCallerIdentity(ctx, &sts.GetCallerIdentityInput{})
	if err != nil {
		return "", fmt.Errorf("failed to get caller identity: %w", err)
	}
	currentAccountID := aws.ToString(callerIdentity.Account)

	if currentAccountID != masterAccountID {
		return "", hError(http.StatusBadRequest, "This is not the root account. Exiting.")
	}

	// Step 2: List all accounts and find the target sub-account.
	accounts, err := listOrganizationAccounts(ctx, orgClient)
	if err != nil {
		return "", err
	}

	subAccount, err := findAccountByName(accounts, awsSubAccountName)
	if err != nil {
		return "", err
	}
	subAccountID := aws.ToString(subAccount.Id)
	slog.Info("found sub-account", "name", awsSubAccountName, "id", subAccountID)

	// Step 3: Assume role in the sub-account.
	roleARN := fmt.Sprintf("arn:aws:iam::%s:role/OrganizationAccountAccessRole", subAccountID)
	assumeRoleOutput, err := stsClient.AssumeRole(ctx, &sts.AssumeRoleInput{
		RoleArn:         aws.String(roleARN),
		RoleSessionName: aws.String(stsSessionName),
	})
	if err != nil {
		return "", fmt.Errorf("failed to assume role in sub-account %s: %w", subAccountID, err)
	}

	// Step 4: Create IAM client with assumed role credentials.
	assumedCreds := assumeRoleOutput.Credentials
	iamCfg := aws.Config{
		Region: hardcodedRegion,
		Credentials: credentials.NewStaticCredentialsProvider(
			aws.ToString(assumedCreds.AccessKeyId),
			aws.ToString(assumedCreds.SecretAccessKey),
			aws.ToString(assumedCreds.SessionToken),
		),
	}
	iamClient := iam.NewFromConfig(iamCfg)

	// Step 5: Create IAM user (skip if already exists, but still create access key).
	_, err = iamClient.CreateUser(ctx, &iam.CreateUserInput{
		UserName: aws.String(iamUserName),
	})
	if err != nil {
		var apiErr smithy.APIError
		if errors.As(err, &apiErr) && apiErr.ErrorCode() == "EntityAlreadyExists" {
			slog.Info("IAM user already exists, skipping creation", "user", iamUserName)
		} else {
			return "", fmt.Errorf("failed to create IAM user: %w", err)
		}
	} else {
		// Only attach policy on new user creation (matching Python behavior).
		_, err = iamClient.AttachUserPolicy(ctx, &iam.AttachUserPolicyInput{
			UserName:  aws.String(iamUserName),
			PolicyArn: aws.String(iamPolicyARN),
		})
		if err != nil {
			return "", fmt.Errorf("failed to attach policy to IAM user: %w", err)
		}
	}

	// Create access key for the user (always, even if user already existed).
	keyOutput, err := iamClient.CreateAccessKey(ctx, &iam.CreateAccessKeyInput{
		UserName: aws.String(iamUserName),
	})
	if err != nil {
		return "", fmt.Errorf("failed to create access key: %w", err)
	}
	accessKey := aws.ToString(keyOutput.AccessKey.AccessKeyId)
	secretKey := aws.ToString(keyOutput.AccessKey.SecretAccessKey)

	// Step 6: Create IAM role with trust policy (skip if already exists).
	trustPolicy := map[string]interface{}{
		"Version": "2012-10-17",
		"Statement": []map[string]interface{}{
			{
				"Effect": "Allow",
				"Principal": map[string]string{
					"AWS": fmt.Sprintf("arn:aws:iam::%s:root", subAccountID),
				},
				"Action": "sts:AssumeRole",
			},
		},
	}
	trustPolicyJSON, err := json.Marshal(trustPolicy)
	if err != nil {
		return "", fmt.Errorf("failed to marshal trust policy: %w", err)
	}

	_, err = iamClient.CreateRole(ctx, &iam.CreateRoleInput{
		RoleName:                 aws.String(iamRoleName),
		AssumeRolePolicyDocument: aws.String(string(trustPolicyJSON)),
	})
	if err != nil {
		var apiErr smithy.APIError
		if errors.As(err, &apiErr) && apiErr.ErrorCode() == "EntityAlreadyExists" {
			slog.Info("IAM role already exists, skipping creation", "role", iamRoleName)
		} else {
			return "", fmt.Errorf("failed to create IAM role: %w", err)
		}
	} else {
		_, err = iamClient.AttachRolePolicy(ctx, &iam.AttachRolePolicyInput{
			RoleName:  aws.String(iamRoleName),
			PolicyArn: aws.String(iamPolicyARN),
		})
		if err != nil {
			return "", fmt.Errorf("failed to attach policy to IAM role: %w", err)
		}
	}

	// Get the ARN of the role.
	roleOutput, err := iamClient.GetRole(ctx, &iam.GetRoleInput{
		RoleName: aws.String(iamRoleName),
	})
	if err != nil {
		return "", fmt.Errorf("failed to get IAM role: %w", err)
	}
	roleCreatedARN := aws.ToString(roleOutput.Role.Arn)

	// Step 7: Generate .env content (must match Python output exactly).
	envContent := fmt.Sprintf(`
# Run the following in your codespace environment to create your .env for %s:

cat <<ENV >> $(pwd)/.env
export AWS_ACCESS_KEY_ID=%s
export AWS_SECRET_ACCESS_KEY=%s
export AWS_DEFAULT_REGION=us-west-2
#aws eks update-kubeconfig --region us-west-2 --name captain-cluster --role-arn %s
ENV

# Here is the iam_role_to_assume that you will need to specify in your terraform module for %s:
# %s

    `, awsSubAccountName, accessKey, secretKey, roleCreatedARN, awsSubAccountName, roleCreatedARN)

	return envContent, nil
}
