package util

import (
	"fmt"

	"github.com/danielgtaylor/huma/v2"
)

// PlainTextResponse is the established pattern for returning plain-text responses
// from Huma v2 handlers. Tickets 04, 06, 07, 08, 10 should use this pattern.
//
// Huma v2's typed handlers have signature:
//
//	func(ctx context.Context, input *Input) (*Output, error)
//
// There is no huma.Context available in typed handlers. For plain text responses,
// use a response struct with `Body func(ctx huma.Context)` — this is the
// huma.StreamResponse type, which gives access to ctx.SetHeader() and
// ctx.BodyWriter().
//
// Usage in a handler:
//
//	func MyHandler(ctx context.Context, input *MyInput) (*util.PlainTextResponse, error) {
//	    result := "plain text content here"
//	    return util.NewPlainTextResponse(result), nil
//	}
type PlainTextResponse struct {
	Body func(ctx huma.Context)
}

// NewPlainTextResponse creates a PlainTextResponse that writes the given string
// as text/plain; charset=utf-8.
func NewPlainTextResponse(text string) *PlainTextResponse {
	return &PlainTextResponse{
		Body: func(ctx huma.Context) {
			ctx.SetHeader("Content-Type", "text/plain; charset=utf-8")
			_, _ = fmt.Fprint(ctx.BodyWriter(), text)
		},
	}
}
