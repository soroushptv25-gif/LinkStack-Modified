# Part of the Digital Business Card module.
# The old per-card override fields (job_title/company/email/phone/website/photo)
# became the explicit MASK fields (mask_*). Carry any existing override values
# over so nothing is lost. The old columns still exist at migrate time.


def migrate(cr, version):
    for old, new in (
        ('job_title', 'mask_job_title'),
        ('company', 'mask_company'),
        ('email', 'mask_email'),
        ('phone', 'mask_phone'),
        ('website', 'mask_website'),
    ):
        cr.execute("""
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'digital_business_card' AND column_name = %s
        """, (old,))
        if not cr.fetchone():
            continue
        cr.execute("""
            UPDATE digital_business_card
               SET {new} = {old}
             WHERE {old} IS NOT NULL AND {old} != ''
               AND ({new} IS NULL OR {new} = '')
        """.format(new=new, old=old))

    # Binary attachment field: reassign the stored attachments from the old
    # 'photo' field name to the new 'mask_photo'.
    cr.execute("""
        UPDATE ir_attachment
           SET res_field = 'mask_photo'
         WHERE res_model = 'digital.business.card'
           AND res_field = 'photo'
    """)
