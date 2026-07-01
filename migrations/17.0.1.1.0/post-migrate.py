# Part of the Digital Business Card module.
# Introduces the draft/published/deactivated workflow: any card that already
# had a link (slug) was effectively "published", so mark it as such instead of
# letting it fall back to the new 'draft' default.


def migrate(cr, version):
    cr.execute("""
        UPDATE digital_business_card
           SET state = 'published'
         WHERE slug IS NOT NULL
           AND slug != ''
           AND (state IS NULL OR state = 'draft')
    """)
