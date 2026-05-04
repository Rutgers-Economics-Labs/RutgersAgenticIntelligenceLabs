# Source Notes

## DOGE API

- Docs: https://api.doge.gov/docs
- OpenAPI: https://api.doge.gov/openapi.json
- Version observed on 2026-05-03: `0.0.2-beta`

## Payments

- `/payments` returns payment line items.
- Documented fields include `payment_date`, `payment_amt`, `agency_name`,
  `award_description`, `fain`, `recipient_justification`,
  `agency_lead_justification`, `org_name`, and
  `generated_unique_award_id`.
- Supported filters are documented for `agency_name`, `date`, and `org_name`.
- Supported sorts are documented for `amount` and `date`.
- The docs explicitly state that the current payment feed includes a limited
  amount of grant payments issued from the Program Support Center and is
  intended to expand over time.

## Payment Statistics

- `/payments/statistics` returns grouped counts.
- Current documented groups are:
  - agency counts
  - request date counts
  - organization name counts

## Savings

- `/savings/grants`, `/savings/contracts`, and `/savings/leases` are separate
  DOGE feeds focused on reported savings rather than payment disbursements.
- Contract savings records expose fields such as `piid`, `vendor`,
  `fpds_status`, and `fpds_link`.
- Grant savings records may expose a `link` to USASpending.

## Cautions

- Payment coverage should not be treated as government-wide until validated.
- Savings claims and payment records are related conceptually but may not be
  directly joinable in practice.
