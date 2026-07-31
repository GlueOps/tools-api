# Changelog

## [0.7.0](https://github.com/GlueOps/tools-api/compare/v0.6.1...v0.7.0) (2026-07-31)


### Features

* slim cloud-init to the baked image and prune stale cached images ([#93](https://github.com/GlueOps/tools-api/issues/93)) ([a83cc89](https://github.com/GlueOps/tools-api/commit/a83cc899b9af2bfaa65f3801c724070973dd96e3))

## [0.6.1](https://github.com/GlueOps/tools-api/compare/v0.6.0...v0.6.1) (2026-07-31)


### Bug Fixes

* default PROXMOX_DOWNLOAD_SERVER_URL to the prebuilt image release ([#91](https://github.com/GlueOps/tools-api/issues/91)) ([c64847b](https://github.com/GlueOps/tools-api/commit/c64847b348befb7d10d08429d10b816295a02503))

## [0.6.0](https://github.com/GlueOps/tools-api/compare/v0.5.1...v0.6.0) (2026-07-31)


### Features

* update docker/setup-buildx-action to v4.1.0 #minor ([#70](https://github.com/GlueOps/tools-api/issues/70)) ([ffa55b4](https://github.com/GlueOps/tools-api/commit/ffa55b4f1602e3b3d7717509b1bde4e81944e765))


### Bug Fixes

* skip docker install when the image already ships docker ([#88](https://github.com/GlueOps/tools-api/issues/88)) ([93aa26b](https://github.com/GlueOps/tools-api/commit/93aa26b107ed9e4cf411f06e040ae42f73cf815f))

## [0.5.1](https://github.com/GlueOps/tools-api/compare/v0.5.0...v0.5.1) (2026-07-31)


### Bug Fixes

* harden k3d-lb cleanup and retries per Proxmox expert review ([#86](https://github.com/GlueOps/tools-api/issues/86)) ([32915c2](https://github.com/GlueOps/tools-api/commit/32915c21aa25f698b44cd6a4047a77dbf6cccd1f))

## [0.5.0](https://github.com/GlueOps/tools-api/compare/v0.4.0...v0.5.0) (2026-07-31)


### Features

* prefix cloud-init ISOs with tools-api and skip in-use ISOs in the sweep ([#85](https://github.com/GlueOps/tools-api/issues/85)) ([6991fce](https://github.com/GlueOps/tools-api/commit/6991fce5fedb38682f3540ccf4ee83916f877a8f))


### Bug Fixes

* retry vmid conflicts reported as atomic-rename 'File exists' errors ([#83](https://github.com/GlueOps/tools-api/issues/83)) ([7636ac6](https://github.com/GlueOps/tools-api/commit/7636ac609a90d982a2626216b0d4ab3593bf170c))

## [0.4.0](https://github.com/GlueOps/tools-api/compare/v0.3.1...v0.4.0) (2026-07-31)


### Features

* update docker/metadata-action to v6.1.0 #minor ([#69](https://github.com/GlueOps/tools-api/issues/69)) ([baa05f8](https://github.com/GlueOps/tools-api/commit/baa05f8b3b59d34f50cceeb27e9c2e6ca9185b47))


### Bug Fixes

* build k3d-lb VMs concurrently instead of one at a time ([#82](https://github.com/GlueOps/tools-api/issues/82)) ([e4db6ed](https://github.com/GlueOps/tools-api/commit/e4db6edebd48b8a6635280d683467070acd11f6d))
* return k3d-lb manifest as soon as IPs are known instead of waiting for full cloud-init ([#80](https://github.com/GlueOps/tools-api/issues/80)) ([aee133d](https://github.com/GlueOps/tools-api/commit/aee133d24ceb809f2aff53331b0ab42799158473))

## [0.3.1](https://github.com/GlueOps/tools-api/compare/v0.3.0...v0.3.1) (2026-07-31)


### Bug Fixes

* default k3d-lb image download to the official Debian cloud images site ([#79](https://github.com/GlueOps/tools-api/issues/79)) ([902d29d](https://github.com/GlueOps/tools-api/commit/902d29de80a08549f706102c840bf16e10c2c789))


### Documentation

* reflect removal of CLI release automation ([#77](https://github.com/GlueOps/tools-api/issues/77)) ([6fe2046](https://github.com/GlueOps/tools-api/commit/6fe204651d8a374a2c56160372a15c754e57704d))

## [0.3.0](https://github.com/GlueOps/tools-api/compare/v0.2.0...v0.3.0) (2026-07-31)


### Features

* add /v1/k3d-lb-nodes endpoint (Chisel nodes on Proxmox via Waggle) ([#76](https://github.com/GlueOps/tools-api/issues/76)) ([4d4a3f9](https://github.com/GlueOps/tools-api/commit/4d4a3f9bdcf1261cc6ed7e6b706c2230ad4cbc3b))
* update dataaxiom/ghcr-cleanup-action to v1.2.2 #minor ([#66](https://github.com/GlueOps/tools-api/issues/66)) ([2b10191](https://github.com/GlueOps/tools-api/commit/2b10191feb343a6eada46fe2d3914929df754da3))
* update docker/build-push-action to v7.3.0 #minor ([#75](https://github.com/GlueOps/tools-api/issues/75)) ([1774968](https://github.com/GlueOps/tools-api/commit/17749682bee9a9dd7237dc76688a3c167b6308cd))


### Miscellaneous Chores

* add Apache-2.0 LICENSE ([#61](https://github.com/GlueOps/tools-api/issues/61)) ([6b18040](https://github.com/GlueOps/tools-api/commit/6b180408a21be1f3c47ed0f06ff06954a367b038))
* **deps:** update python base image digest and CI action versions ([#63](https://github.com/GlueOps/tools-api/issues/63)) ([5cb0fee](https://github.com/GlueOps/tools-api/commit/5cb0fee9a432dd00983b4d5c8c23aa7d83ab0a6d))

## [0.2.0](https://github.com/GlueOps/tools-api/compare/v0.1.1...v0.2.0) (2026-07-27)


### Features

* add vpa rbac (read-only) ([#59](https://github.com/GlueOps/tools-api/issues/59)) ([4202dac](https://github.com/GlueOps/tools-api/commit/4202dacee6823759e4283651bbc5a46c77e065d2))

## [0.1.1](https://github.com/GlueOps/tools-api/compare/v0.1.0...v0.1.1) (2026-07-06)


### Bug Fixes

* generate valid, consistently-indented storage config YAML ([#54](https://github.com/GlueOps/tools-api/issues/54)) ([8e01d79](https://github.com/GlueOps/tools-api/commit/8e01d7984c1283f8909e7245757b209976b4bd83))

## [0.1.0](https://github.com/GlueOps/tools-api/compare/v0.0.72...v0.1.0) (2026-06-30)


### Features

* consolidate dependency updates ([#53](https://github.com/GlueOps/tools-api/issues/53)) ([84a3a7e](https://github.com/GlueOps/tools-api/commit/84a3a7edca6817612347612661ccf9d0dd261ec1))


### Continuous Integration

* add release-please ([#51](https://github.com/GlueOps/tools-api/issues/51)) ([322d347](https://github.com/GlueOps/tools-api/commit/322d347c7ab5060b08a2f8825f66d11004f368db))
