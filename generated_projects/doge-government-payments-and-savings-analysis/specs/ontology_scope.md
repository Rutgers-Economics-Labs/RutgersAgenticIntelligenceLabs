# Ontology And Scope Plan

## Why This Ontology

The DOGE API currently exposes two analytically different surfaces:

- transaction-like payment records
- event-like savings records

The ontology should preserve that distinction so later analysis does not imply a
direct one-to-one relationship that the source does not document.

## Phase One Classes

### PaymentRecord

Represents one DOGE payment line item from `/payments`.

Core properties:

- `paymentDate`
- `paymentAmount`
- `awardDescription`
- `recipientJustification`
- `agencyLeadJustification`
- `generatedUniqueAwardId`
- `fain`

Links:

- belongs to `Agency`
- paid to `Organization`

### PaymentStatisticsBucket

Represents an aggregate count bucket from `/payments/statistics`.

Core properties:

- `bucketType`
- `bucketLabel`
- `bucketCount`
- `observationDate`

Notes:

- This class should not be merged into `PaymentRecord`.
- It exists for endpoint-level summary analytics and quick profiling.

### SavingsRecord

Represents one DOGE savings entry from grants, contracts, or leases endpoints.

Core properties:

- `recordType`
- `eventDate`
- `value`
- `savingsAmount`
- `description`

Optional subtype-specific fields:

- contract: `piid`, `vendor`, `fpdsStatus`, `fpdsLink`
- grant: `recipient`, `link`
- lease: `location`, `sqFt`

### Agency

Normalized federal agency entity used by both payments and savings records.

### Organization

Normalized recipient or vendor entity.

## Phase One Scope Of Work

1. Validate the live shape of `/payments` and `/payments/statistics`.
2. Confirm pagination, null behavior, and filter behavior.
3. Produce a simple agency and recipient profile from payment statistics.
4. Review a sample of justifications for recurring themes or weak explanations.
5. Inventory what identifiers might support linkage across DOGE, USASpending,
   and FPDS.

## Phase Two Scope Of Work

1. Expand savings ingestion into separate grant, contract, and lease manifests.
2. Add normalization rules for agencies and organizations.
3. Build joins or probabilistic linkage only if identifiers support it.
4. Create artifacts such as notebooks, dashboards, or exported research tables.

## Non-Goals For Now

- claiming full federal payment coverage
- claiming direct causal relationships from descriptive API slices
- forcing cross-endpoint linkage without identifier evidence
