{
    'name': 'Digital Business Card',
    'version': '1.0.0',
    'category': 'Marketing',
    'summary': 'Shareable digital business cards with a permanent link and an auto-generated QR code.',
    'description': """
Digital Business Card
=====================

A native Odoo take on the "link in bio" / digital business card idea
(inspired by LinkStack, which is a PHP/Laravel app and cannot be embedded
directly — this module reimplements the concept in Python/XML/QWeb).

Features
--------
* A ``digital.business.card`` record per person: name, title, company,
  contact details, photo and bio.
* Every card gets a **permanent public link** at ``/card/<slug>``.
* A **QR code** is generated automatically (Odoo's built-in barcode engine)
  and always points at that permanent link.
* A public, no-login card page so the card can be shared by URL or QR.

A dormant ``create_card_from_html_file`` helper is included for later use
(building a card from an external HTML file). It is intentionally not wired
up to any button, route or cron yet.
""",
    'author': 'Soroush',
    'website': 'https://github.com/',
    'depends': ['base', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'security/business_card_rules.xml',
        'views/business_card_templates.xml',
        'views/business_card_views.xml',
        'views/business_card_source_views.xml',
        'views/business_card_target_views.xml',
        'views/business_card_menus.xml',
    ],
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
}
