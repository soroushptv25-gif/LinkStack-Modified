# Part of the Digital Business Card module.
#
# A configurable external data source: the admin "plugs in" a server (a
# PostgreSQL connection OR an HTTP URL), and this pulls person records whose
# body is stored as HTML, then creates/updates business cards from them.
import json
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

from .net_utils import MAX_HTTP_BYTES, assert_url_allowed

_logger = logging.getLogger(__name__)


class DigitalBusinessCardSource(models.Model):
    _name = 'digital.business.card.source'
    _description = 'Business Card Data Source'
    _order = 'name asc'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    source_type = fields.Selection(
        [('sql', 'SQL database (PostgreSQL)'), ('http', 'HTTP / URL')],
        string='Source Type', required=True, default='sql')

    # --- SQL connection (PostgreSQL) -------------------------------------
    db_host = fields.Char(string='Host', default='localhost')
    db_port = fields.Integer(string='Port', default=5432)
    db_name = fields.Char(string='Database')
    db_user = fields.Char(string='Username')
    db_password = fields.Char(string='Password', copy=False)
    db_table = fields.Char(string='Table', help="Table with one person per row.")
    col_slug = fields.Char(string='Key/Slug Column',
                           help="Column used as the card's unique slug/link.")
    col_html = fields.Char(string='HTML Column',
                           help="Column that stores the person's HTML.")
    col_name = fields.Char(string='Name Column (optional)',
                           help="Column for the display name; falls back to the slug.")
    row_limit = fields.Integer(string='Max Rows', default=100)

    # --- HTTP source -----------------------------------------------------
    http_url = fields.Char(string='URL')
    http_token = fields.Char(string='Auth Token (optional)', copy=False,
                             help="Sent as 'Authorization: Bearer <token>'.")

    # Off by default: the HTTP fetcher refuses private/loopback/link-local
    # addresses (SSRF guard). Turn on only for a trusted internal source.
    allow_private = fields.Boolean(
        string='Allow internal addresses', default=False,
        help="Permit the HTTP source to reach private/internal IPs. "
             "Leave off unless you trust the target network.")

    last_sync = fields.Datetime(string='Last Import', readonly=True)
    last_count = fields.Integer(string='Cards From Last Import', readonly=True)

    # ------------------------------------------------------------------
    # Buttons (the easy-to-use entry points)
    # ------------------------------------------------------------------
    def action_test_connection(self):
        """Reach the source without importing anything."""
        self.ensure_one()
        self._fetch_rows(test_only=True)
        return self._notify('Connection OK',
                            'Reached the source successfully.', 'success')

    def action_import_cards(self):
        """Pull every person row and create/update a card for each."""
        self.ensure_one()
        rows = self._fetch_rows()
        count = self._upsert_cards(rows)
        self.write({'last_sync': fields.Datetime.now(), 'last_count': count})
        return self._notify('Import complete',
                            '%s card(s) created or updated.' % count, 'success')

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------
    def _fetch_rows(self, test_only=False):
        """Return a list of {slug, name, html} dicts from the source."""
        self.ensure_one()
        if self.source_type == 'sql':
            return self._fetch_rows_sql(test_only=test_only)
        return self._fetch_rows_http(test_only=test_only)

    def _fetch_rows_sql(self, test_only=False):
        import psycopg2  # ships with Odoo
        for fname in ('db_host', 'db_name', 'db_user', 'db_table', 'col_slug', 'col_html'):
            if not self[fname]:
                raise UserError("Please fill in the SQL field: %s" % fname)

        # Table/column names are identifiers — they can't be bound as query
        # parameters, so quote them and strip any embedded quotes defensively.
        def ident(value):
            return '"%s"' % str(value).replace('"', '')

        columns = [self.col_slug, self.col_html]
        if self.col_name:
            columns.append(self.col_name)
        limit = max(1, self.row_limit or 100)
        query = 'SELECT %s FROM %s LIMIT %s' % (
            ', '.join(ident(c) for c in columns), ident(self.db_table), int(limit))

        conn = None
        try:
            conn = psycopg2.connect(
                host=self.db_host, port=self.db_port or 5432,
                dbname=self.db_name, user=self.db_user,
                password=self.db_password or '', connect_timeout=10)
            # We only ever read; force the session read-only so a bug or a
            # crafted table/column name can never write to the foreign DB.
            conn.set_session(readonly=True, autocommit=True)
            cur = conn.cursor()
            if test_only:
                cur.execute('SELECT 1')
                cur.fetchone()
                return []
            cur.execute(query)
            records = cur.fetchall()
        except Exception as e:
            raise UserError("SQL source error: %s" % e)
        finally:
            if conn:
                conn.close()

        rows = []
        for rec in records:
            slug = rec[0]
            if slug is None:
                continue
            html = rec[1] or ''
            name = rec[2] if (self.col_name and len(rec) > 2 and rec[2]) else slug
            rows.append({'slug': str(slug), 'html': html, 'name': str(name)})
        return rows

    def _fetch_rows_http(self, test_only=False):
        import requests  # ships with Odoo
        if not self.http_url:
            raise UserError("Please fill in the URL.")
        assert_url_allowed(self.http_url, self.allow_private)
        headers = {}
        if self.http_token:
            headers['Authorization'] = 'Bearer %s' % self.http_token
        try:
            # allow_redirects=False: a redirect could otherwise bounce us to an
            # internal address after the SSRF check has already passed.
            resp = requests.get(self.http_url, headers=headers, timeout=15,
                                allow_redirects=False, stream=True)
            resp.raise_for_status()
            # Read with a hard size cap so a huge/hostile body can't OOM us.
            chunks, total = [], 0
            for chunk in resp.iter_content(8192):
                total += len(chunk)
                if total > MAX_HTTP_BYTES:
                    raise UserError("Response is larger than the 5 MB limit.")
                chunks.append(chunk)
        except UserError:
            raise
        except Exception as e:
            raise UserError("HTTP source error: %s" % e)
        finally:
            resp_close = getattr(locals().get('resp', None), 'close', None)
            if resp_close:
                resp_close()
        if test_only:
            return []

        body = b''.join(chunks).decode(resp.encoding or 'utf-8', errors='replace')
        ctype = resp.headers.get('Content-Type', '')
        # A JSON list/array of people -> many cards. Anything else -> treat the
        # whole response body as one person's HTML.
        if 'application/json' in ctype or body.strip()[:1] in ('[', '{'):
            try:
                data = json.loads(body)
            except ValueError:
                data = None
            if isinstance(data, dict):
                data = data.get('data') or data.get('results') or [data]
            if isinstance(data, list):
                rows = []
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    slug = item.get('slug') or item.get('id') or item.get('username')
                    if slug is None:
                        continue
                    rows.append({
                        'slug': str(slug),
                        'html': item.get('html') or item.get('content') or '',
                        'name': str(item.get('name') or slug),
                    })
                return rows
        slug = self.http_url.rstrip('/').split('/')[-1] or 'imported'
        return [{'slug': slug, 'html': body, 'name': slug}]

    # ------------------------------------------------------------------
    # Upsert: create new cards or refresh existing ones (matched by slug).
    # ------------------------------------------------------------------
    def _upsert_cards(self, rows):
        Card = self.env['digital.business.card']
        count = 0
        for row in rows:
            slug = (row.get('slug') or '').strip()
            if not slug:
                continue
            vals = {'name': row.get('name') or slug, 'source_html': row.get('html') or ''}
            card = Card.with_context(active_test=False).search(
                [('slug', '=', slug)], limit=1)
            if card:
                card.write(vals)
            else:
                Card.create(dict(vals, slug=slug))
            count += 1
        return count

    def _notify(self, title, message, ntype):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': title, 'message': message,
                       'type': ntype, 'sticky': False},
        }
