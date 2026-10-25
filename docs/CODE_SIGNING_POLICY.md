# Code signing policy

## Current status

Woer Translator is seeking free Windows code signing through the SignPath
Foundation program. The application has not been approved and no SignPath
certificate has been issued for this project. Existing v0.2.0 Windows downloads
are unsigned. This page does not claim sponsorship, endorsement or a signed
release before approval.

## Project and review contacts

- Repository and release maintainer: [blueaaa333](https://github.com/blueaaa333).
- Proposed signing approver: the repository owner, blueaaa333. A signing request
  must receive the maintainer's explicit manual approval before signing.
- Contributors' changes and build-workflow changes must be reviewed by the
  maintainer before they are selected for a signed release.
- Before signing is activated, the maintainer must satisfy SignPath's account
  security and multi-factor authentication requirements. This document does not
  attest that SignPath has already verified those requirements.

## Build provenance and scope

Windows releases are built from a public Git commit using
[GitHub Actions](../.github/workflows/release.yml). The application and its native
selection helper are built from source; the Windows installer is created with
Inno Setup. Automated checks cover the public dictionaries, native helper,
frozen application resources, and desktop interface.

Only this project's own executable artifacts and installers would be submitted
for signing. Third-party runtime libraries retain their upstream identity and
licenses. Piper runtime binaries and voice models are not bundled in installers;
users may explicitly download them directly from their upstreams. Apple system
voices are not distributed. The mixed code/data licensing structure is disclosed
in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) for eligibility review.

There is currently no active SignPath integration. If accepted, signature and
product/version metadata checks will be added before the first signed release.
The required attribution, "Free code signing provided by SignPath.io,
certificate by SignPath Foundation", will be displayed for releases actually
signed under that program. It is not a description of the current unsigned files.

## Privacy

[Privacy policy](PRIVACY.md): dictionary lookups and speech synthesis run locally.
Selected text and queries are not uploaded to a lookup or analytics service.
Users can explicitly open source links or download optional dependencies; those
actions make ordinary network requests to the chosen upstream. Settings,
vocabulary lists, diagnostic logs and speech caches remain on the local device.

If signing is approved, any signing-service permissions will be limited to the
necessary project and approved release workflow. Account access and permission
grants require the maintainer's explicit authorization.
