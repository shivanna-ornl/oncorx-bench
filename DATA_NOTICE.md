# Data provenance and redistribution notice

The source-code license, if one is later declared for this repository, does not
automatically apply to third-party data or data-derived knowledge views.

Files under `data/knowledge/` are deterministic benchmark views derived from
the Unified Oncology Treatment Database (UOTD) release pinned in
`data/knowledge/provenance.json`. UOTD integrates sources with their own terms.
Its project notice states that its code license does not grant rights to
redistribute third-party source data. Users remain responsible for reviewing
UOTD and upstream terms before redistribution or commercial use.

To reduce unnecessary republication, `drug_table.csv` contains only the 241
canonical drug anchors needed by this benchmark release and empty alias arrays;
it does not copy UOTD's full synonym inventory. `regimen_table.csv` contains a
conservative 492-row benchmark projection, and
`Conditions_And_Regimens.csv` contains the 804 condition associations that
resolve to those eligible regimens. These reductions improve auditability but
do not create a new license grant.

The 2,000 records under `output/` are automatically generated synthetic text
and annotations. They contain no patient records. They have not been
independently clinically adjudicated and are not intended for clinical use.
