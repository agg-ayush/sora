---
name: adobe-sign-v6-prefill
description: Use when prefilling Adobe Sign v6 agreement form fields.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [Adobe, Acrobat Sign, REST API, Forms]
    related_skills: [research]
---

# Adobe Acrobat Sign v6 form values

## When to Use

Use when implementing or troubleshooting Acrobat Sign v6 agreement form fields, prefill defaults, or post-send field retrieval.

- Fetch the **live** [OpenAPI](https://secure.na1.adobesign.com/restapijson/v6/restapi.json) before implementing; inspect `AgreementCreationInfo`, `MergefieldInfo`, `FormFieldMergeInfo`, and agreement form-field paths rather than trusting SDK examples or guessed `formFieldValues` names.
- For creation, use `mergeFieldInfo: [{"fieldName":"<existing-name>","defaultValue":"<value>"}]` on `POST /agreements`. `fieldName` must correspond to a generated/authored form field, not a visually printed PDF label.
- In `AUTHORING`, inspect `GET /agreements/{agreementId}/formFields`, then `PUT /agreements/{agreementId}/formFields/mergeInfo` with `{"fieldMergeInfos":[{"fieldName":"<existing-name>","defaultValue":"<value>"}]}`. Read it back before transitioning with `PUT /agreements/{agreementId}/state` body `{"state":"IN_PROCESS"}`.
- Add/edit **field definitions** via `PUT /agreements/{agreementId}/formFields` only in `AUTHORING`; the live spec documents 403 `AGREEMENT_NOT_IN_AUTHORING_STATE`. Text-tag and generator fields are not modifiable until entering AUTHORING. Avoid treating `IN_REVISION` as full authoring.
- After send, use `GET /agreements/{agreementId}/formData?allowInProcessAgreement=true` to read existing signer data as the agreement creator. There is no documented `PUT /formData` or `formFieldValues` property in the v6 schema. `GET /members` gives participant IDs/status, not field values.
- Distinguish a stable library document's named fields (`GET /libraryDocuments/{id}/formFields`), an uploaded transient PDF with Acrobat Sign text tags, actual existing AcroForm field objects (Adobe says it converts them on upload/send), and mere visual blanks (no guaranteed named field). Process an actual PDF in AUTHORING and inspect names, assignments, read-only flags, and content types; account-specific flattening may change outcomes.
- Leave signature/name/date system fields to Acrobat Sign. Its HelpX documentation says signer name and signature date are automatically populated and signer-read-only, whereas signer title auto-populates only if known and may need signer entry. The v6 schema allows merge values for read-only fields generally; it does not establish a universal ban on sender values for every system field, so avoid making that stronger claim without an account test.
- Adobe HelpX may block live retrieval; if using an archived Adobe-authored copy, cite its snapshot URL and date explicitly. Prefer live OpenAPI for endpoint conditions when an older release note conflicts.

Detailed cited research artifact: `/home/ubuntu/.sherlock/sessions/7a4e40c1/report/prefill.md`.
