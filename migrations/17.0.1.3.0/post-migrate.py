# Part of the Digital Business Card module.
# The public URL now uses an unguessable access token instead of the slug.
# Mint a token for every already-published card so its link keeps working.
import uuid


def migrate(cr, version):
    cr.execute("""
        SELECT id FROM digital_business_card
         WHERE state = 'published'
           AND (access_token IS NULL OR access_token = '')
    """)
    for (card_id,) in cr.fetchall():
        cr.execute(
            "UPDATE digital_business_card SET access_token = %s WHERE id = %s",
            (uuid.uuid4().hex, card_id),
        )
