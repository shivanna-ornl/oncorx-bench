# Data-quality status

The current release passes the automated structural gate with zero errors. The
gate checks all 2,000 sequential identifiers and quotas; strict nested fields,
types, and enums; canonical drug, regimen, and component foreign keys; exact
surface offsets; visible intent, cycle, adverse-event, and sig evidence;
normalized-drug counts; unresolved placeholders; duplicate text and duplicate
annotations; and nonzero failure status.

The split is subcategory-stratified and template-grouped: it contains exactly
1,600 training and 400 test records, with no source template shared across the
two partitions. It remains an in-domain synthetic split; drug and regimen
entities may occur in both partitions.

Automated consistency is not clinical adjudication. Dose/route values are
drawn only from versioned author-specified profiles and arbitrary generic
fallbacks are prohibited, but the profiles and generated combinations have not
been independently reviewed as treatment recommendations. The conservative
UOTD projection reduces known component-collision risk but does not prove that
every retained condition--regimen relationship is clinically correct.

Before claiming clinical validity, the release still needs blinded oncology
pharmacology/clinical review with recorded adjudication. Before claiming broad
linguistic or model generalization, it also needs evaluation on real clinical
corpora and stronger entity- and regimen-disjoint partitions.
