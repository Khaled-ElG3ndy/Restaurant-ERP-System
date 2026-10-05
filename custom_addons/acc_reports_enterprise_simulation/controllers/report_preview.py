# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import re
import unicodedata
import base64
from io import BytesIO

import lxml.html
import xlsxwriter

from odoo import http
from odoo.http import content_disposition, request
from odoo.tools.misc import html_escape


class AccountingReportPreviewController(http.Controller):
    def _active_ids_from_context(self, context):
        active_ids = context.get('active_ids') or []
        active_id = context.get('active_id')
        if active_id and not active_ids:
            active_ids = [active_id]
        return active_ids

    def _render_report_html(self, report, data, context, search_term=None, rendered_html=None):
        if rendered_html:
            return self._move_currency_symbol_after_amount(self._strip_report_action_nodes(rendered_html))
        report_env = request.env['ir.actions.report'].with_context(**context).sudo()
        html_content = report_env.with_context(debug=False)._render_qweb_html(
            report.report_name,
            self._active_ids_from_context(context),
            data=data,
        )[0]
        html_content = self._apply_export_search_filter(html_content, search_term)
        return self._move_currency_symbol_after_amount(self._strip_report_action_nodes(html_content))

    def _render_pdf_data(self, report, data, context, search_term=None, rendered_html=None):
        report_env = request.env['ir.actions.report'].with_context(
            **context,
            acc_report_preview_export=True,
        ).sudo()
        active_ids = self._active_ids_from_context(context)
        if rendered_html or (search_term or '').strip():
            html_content = self._render_report_html(report, data, context, search_term, rendered_html)
            report_sudo = report.sudo().with_context(
                **context,
                acc_report_preview_export=True,
                debug=False,
            )
            bodies, _html_ids, header, footer, specific_paperformat_args = report_sudo._prepare_html(
                html_content,
                report_model=report_sudo.model,
            )
            return report_sudo._run_wkhtmltopdf(
                bodies,
                report_ref=report.report_name,
                header=header,
                footer=footer,
                landscape=report_sudo.env.context.get('landscape'),
                specific_paperformat_args=specific_paperformat_args,
                set_viewport_size=report_sudo.env.context.get('set_viewport_size'),
            )
        return report_env._render_qweb_pdf(
            report.report_name,
            active_ids,
            data=data,
        )[0]

    @http.route(['/acc_reports_enterprise_simulation/export_pdf'], type='http', auth='user', methods=['POST'], csrf=True)
    def export_pdf(self, report_name, data=None, context=None, display_name=None, search_term=None, rendered_html=None):
        try:
            data = json.loads(data or '{}')
            context = json.loads(context or '{}')
            report = request.env['ir.actions.report']._get_report_from_name(report_name)
            pdf_data = self._render_pdf_data(report, data, context, search_term, rendered_html)
            report_label = display_name or (data.get('form') or {}).get('download_name') or report.name
            headers = [
                ('Content-Type', 'application/pdf'),
                ('Content-Length', len(pdf_data)),
                ('Content-Disposition', content_disposition(f"{report_label}.pdf")),
            ]
            return request.make_response(pdf_data, headers=headers)
        except Exception as e:
            response = request.make_response(http.serialize_exception(e))
            response.status_code = 500
            return response

    @http.route(['/acc_reports_enterprise_simulation/preview_pdf'], type='http', auth='user', methods=['POST'], csrf=True)
    def preview_pdf(self, report_name, data=None, context=None, display_name=None, search_term=None, rendered_html=None):
        try:
            data = json.loads(data or '{}')
            context = json.loads(context or '{}')
            report = request.env['ir.actions.report']._get_report_from_name(report_name)
            pdf_data = self._render_pdf_data(report, data, context, search_term, rendered_html)
            report_label = display_name or (data.get('form') or {}).get('download_name') or report.name
            return request.make_response(
                self._build_pdf_preview_page(
                    report_label,
                    pdf_data,
                    {
                        'report_name': report_name,
                        'data': json.dumps(data),
                        'context': json.dumps(context),
                        'display_name': report_label,
                        'search_term': search_term or '',
                        'rendered_html': rendered_html or '',
                    },
                ),
                headers=[('Content-Type', 'text/html; charset=utf-8')],
            )
        except Exception as e:
            response = request.make_response(http.serialize_exception(e))
            response.status_code = 500
            return response

    @http.route(['/acc_reports_enterprise_simulation/export_xlsx'], type='http', auth='user', methods=['POST'], csrf=True)
    def export_xlsx(self, report_name, data=None, context=None, display_name=None, search_term=None, rendered_html=None):
        try:
            data = json.loads(data or '{}')
            context = json.loads(context or '{}')

            report = request.env['ir.actions.report']._get_report_from_name(report_name)
            report_env = request.env['ir.actions.report'].with_context(**context).sudo()
            active_ids = self._active_ids_from_context(context)
            rendering_context = report_env._get_rendering_context(report, active_ids, data)
            html_content = self._render_report_html(report, data, context, search_term, rendered_html)
            report_label = display_name or (data.get('form') or {}).get('download_name') or report.name
            xlsx_data = self._build_xlsx(report.report_name, report_label, rendering_context, html_content=html_content)
            filename = f"{report_label}.xlsx"
            headers = [
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Length', len(xlsx_data)),
                ('Content-Disposition', content_disposition(filename)),
            ]
            return request.make_response(xlsx_data, headers=headers)
        except Exception as e:
            response = request.make_response(http.serialize_exception(e))
            response.status_code = 500
            return response

    @http.route(['/acc_reports_enterprise_simulation/preview_xlsx'], type='http', auth='user', methods=['POST'], csrf=True)
    def preview_xlsx(self, report_name, data=None, context=None, display_name=None, search_term=None, rendered_html=None):
        try:
            data_raw = data or '{}'
            context_raw = context or '{}'
            data_values = json.loads(data_raw)
            context_values = json.loads(context_raw)
            report = request.env['ir.actions.report']._get_report_from_name(report_name)
            html_content = self._render_report_html(report, data_values, context_values, search_term, rendered_html)
            report_label = display_name or (data_values.get('form') or {}).get('download_name') or report.name
            return request.make_response(
                self._build_xlsx_preview_page(
                    report_label,
                    html_content,
                    {
                        'report_name': report_name,
                        'data': data_raw,
                        'context': context_raw,
                        'display_name': report_label,
                        'search_term': search_term or '',
                        'rendered_html': rendered_html or html_content,
                    },
                ),
                headers=[('Content-Type', 'text/html; charset=utf-8')],
            )
        except Exception as e:
            response = request.make_response(http.serialize_exception(e))
            response.status_code = 500
            return response

    def _hidden_export_inputs(self, values):
        values = dict(values)
        values['csrf_token'] = request.csrf_token()
        return ''.join(
            '<input type="hidden" name="%s" value="%s"/>'
            % (html_escape(name), html_escape(value or ''))
            for name, value in values.items()
        )

    def _build_pdf_preview_page(self, report_label, pdf_data, export_values):
        title = html_escape(report_label or 'Report')
        inputs = self._hidden_export_inputs(export_values)
        pdf_base64 = base64.b64encode(pdf_data).decode()
        return f"""<!doctype html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>{title}</title>
    <style>
        html, body {{
            height: 100%;
            margin: 0;
            background: #f5f7fb;
            color: #12223a;
            direction: rtl;
            font-family: "Odoo Unicode Support Noto", "Lucida Grande", Helvetica, Verdana, Arial, "DejaVu Sans", sans-serif;
        }}
        .o_report_preview_toolbar {{
            height: 48px;
            box-sizing: border-box;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            padding: 8px 14px;
            background: #ffffff;
            border-bottom: 1px solid #d8dde6;
        }}
        .o_report_preview_title {{
            min-width: 0;
            font-size: 14px;
            font-weight: 700;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .o_report_preview_download {{
            border: 0;
            border-radius: 4px;
            background: #c7a14d;
            color: #071221;
            padding: 7px 13px;
            font-size: 13px;
            font-weight: 700;
            cursor: pointer;
            white-space: nowrap;
        }}
        .o_report_preview_download:hover {{
            background: #b69242;
        }}
        .o_report_preview_frame {{
            display: block;
            width: 100%;
            height: calc(100% - 48px);
            border: 0;
        }}
    </style>
</head>
<body>
    <div class="o_report_preview_toolbar">
        <div class="o_report_preview_title">{title}</div>
        <form method="post" action="/acc_reports_enterprise_simulation/export_pdf">
            {inputs}
            <button type="submit" class="o_report_preview_download">تحميل PDF</button>
        </form>
    </div>
    <iframe class="o_report_preview_frame" title="{title}" src="data:application/pdf;base64,{pdf_base64}"></iframe>
</body>
</html>"""

    def _build_xlsx_preview_page(self, report_label, html_content, export_values):
        title = html_escape(report_label or 'Report')
        content = self._xlsx_preview_content_html(html_content)
        inputs = self._hidden_export_inputs(export_values)
        return f"""<!doctype html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>{title}</title>
    <style>
        body {{
            height: 100vh;
            margin: 0;
            background: #f5f7fb;
            color: #12223a;
            direction: rtl;
            font-family: "Odoo Unicode Support Noto", "Lucida Grande", Helvetica, Verdana, Arial, "DejaVu Sans", sans-serif;
        }}
        .o_xlsx_preview_toolbar {{
            position: sticky;
            top: 0;
            z-index: 20;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            padding: 12px 18px;
            background: #ffffff;
            border-bottom: 1px solid #d8dde6;
            box-shadow: 0 8px 22px rgba(15, 23, 42, 0.08);
        }}
        .o_xlsx_preview_title {{
            min-width: 0;
            font-size: 15px;
            font-weight: 700;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .o_xlsx_preview_download {{
            border: 0;
            border-radius: 4px;
            background: #c7a14d;
            color: #071221;
            padding: 8px 14px;
            font-size: 13px;
            font-weight: 700;
            cursor: pointer;
            white-space: nowrap;
        }}
        .o_xlsx_preview_download:hover {{
            background: #b69242;
        }}
        .o_xlsx_preview_sheet {{
            box-sizing: border-box;
            max-width: 1280px;
            margin: 24px auto 56px;
            padding: 0 18px;
            overflow-x: auto;
        }}
        .o_xlsx_preview_table {{
            width: 100%;
            border-collapse: collapse;
            table-layout: auto;
            background: #ffffff;
            color: #07172d;
            direction: rtl;
            font-size: 13px;
        }}
        .o_xlsx_preview_table th,
        .o_xlsx_preview_table td {{
            border: 1px solid #d9dee7;
            padding: 7px 10px;
            line-height: 1.35;
            vertical-align: middle;
            text-align: right;
            white-space: normal;
        }}
        .o_xlsx_preview_table th {{
            background: #eef2f7;
            border-color: #c8d0db;
            font-weight: 700;
            text-align: center;
            white-space: nowrap;
        }}
        .o_xlsx_preview_table .text-end,
        .o_xlsx_preview_table .o_value_col,
        .o_xlsx_preview_table .o_period_col,
        .o_xlsx_preview_table .o_aged_amount_col,
        .o_xlsx_preview_table .o_tax_amount,
        .o_xlsx_preview_table .o_acc_financial_amount,
        .o_xlsx_preview_table .o_acc_financial_metric {{
            direction: ltr;
            unicode-bidi: isolate;
            text-align: left;
            white-space: nowrap;
        }}
        .o_xlsx_preview_table .o_total_row td,
        .o_xlsx_preview_table .o_acc_financial_total td {{
            background: #d8dadd;
            border-color: #c8d0db;
            font-weight: 700;
        }}
        .o_xlsx_preview_table .o_acc_financial_group td {{
            background: #f6f8fb;
            font-weight: 700;
        }}
        .o_xlsx_preview_table + .o_xlsx_preview_table {{
            margin-top: 14px;
        }}
        .o_xlsx_preview_lead {{
            margin: 0 0 10px;
            padding: 8px 10px;
            background: #ffffff;
            border: 1px solid #d9dee7;
            color: #07172d;
            font-size: 13px;
            font-weight: 700;
        }}
        @media (max-width: 768px) {{
            .o_xlsx_preview_toolbar {{
                align-items: stretch;
                flex-direction: column;
            }}
            .o_xlsx_preview_title {{
                white-space: normal;
            }}
            .o_xlsx_preview_sheet {{
                margin-top: 14px;
                padding: 0 10px;
            }}
        }}
    </style>
</head>
<body>
    <div class="o_xlsx_preview_toolbar">
        <div class="o_xlsx_preview_title">{title}</div>
        <form method="post" action="/acc_reports_enterprise_simulation/export_xlsx">
            {inputs}
            <button type="submit" class="o_xlsx_preview_download">تحميل XLSX</button>
        </form>
    </div>
    <main class="o_xlsx_preview_sheet">{content}</main>
</body>
</html>"""

    def _xlsx_preview_content_html(self, html_content):
        root = lxml.html.fromstring(self._decode_html(html_content))
        self._strip_export_only_nodes(root)
        fragments = []
        lead_xpaths = [
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_acc_financial_period ')]",
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_acc_financial_balance_label ')]",
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_report_analytic_selection ')]",
        ]
        for xpath in lead_xpaths:
            for node in root.xpath(xpath):
                text = self._normalize_cell_text(node.text_content())
                if text:
                    fragments.append(f'<div class="o_xlsx_preview_lead">{html_escape(text)}</div>')
        for table in root.xpath('//table[.//tr]'):
            table.set('class', '%s o_xlsx_preview_table' % (table.get('class') or ''))
            fragments.append(lxml.html.tostring(table, encoding='unicode'))
        return ''.join(fragments) or '<div class="o_xlsx_preview_lead">لا توجد بيانات</div>'

    def _preview_full_html(self, html_content, report_label):
        root = lxml.html.fromstring(self._decode_html(html_content))
        head = root.xpath('//head')
        if head:
            title = head[0].xpath('./title')
            if title:
                title[0].text = report_label or 'Report'
            else:
                title_node = lxml.html.Element('title')
                title_node.text = report_label or 'Report'
                head[0].append(title_node)
        return lxml.html.tostring(root, encoding='unicode')

    def _preview_body_html(self, html_content):
        root = lxml.html.fromstring(self._decode_html(html_content))
        self._strip_export_only_nodes(root)
        body = root.xpath('//body')
        if body:
            children = list(body[0])
            if children:
                return ''.join(lxml.html.tostring(child, encoding='unicode') for child in children)
            return body[0].text_content()
        return lxml.html.tostring(root, encoding='unicode')

    def _safe_sheet_name(self, value):
        value = re.sub(r'[\[\]:*?/\\]', ' ', value or 'Report').strip() or 'Report'
        return value[:31]

    def _normalize_cell_text(self, value):
        return re.sub(r'\s+', ' ', value or '').strip()

    def _normalize_search_text(self, value):
        value = unicodedata.normalize('NFKD', str(value or ''))
        value = re.sub(r'[\u064B-\u065F\u0670]', '', value)
        value = (
            value
            .replace('إ', 'ا')
            .replace('أ', 'ا')
            .replace('آ', 'ا')
            .replace('ى', 'ي')
            .replace('ؤ', 'و')
            .replace('ئ', 'ي')
            .replace('ة', 'ه')
        )
        return re.sub(r'\s+', ' ', value).strip().lower()

    def _first_attr(self, node, xpath):
        values = node.xpath(xpath)
        return str(values[0]) if values else ''

    def _export_row_keys(self, row):
        account_id = row.get('data-account-row-id') or self._first_attr(
            row,
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_account_line ')]/@data-account-id",
        )
        partner_id = self._first_attr(
            row,
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_partner_line ')]/@data-partner-id",
        )
        return {
            'own': {
                'report': row.get('data-report-id') or '',
                'account': account_id or '',
                'partner': partner_id or '',
                'aged_partner': row.get('data-aged-partner-id') or '',
                'tb': row.get('data-tb-line-key') or '',
            },
            'parent': {
                'report': row.get('data-parent-report-id') or '',
                'account': row.get('data-parent-account-id') or '',
                'partner': row.get('data-parent-partner-id') or '',
                'aged_partner': row.get('data-parent-aged-partner-id') or '',
                'tb': row.get('data-parent-tb-key') or '',
            },
        }

    def _apply_export_search_filter(self, html_content, search_term):
        needle = self._normalize_search_text(search_term)
        if not needle:
            return html_content

        root = lxml.html.fromstring(self._decode_html(html_content))
        rows = root.xpath('//tbody/tr')
        relation_kinds = ('report', 'account', 'partner', 'aged_partner', 'tb')
        matching_rows = {}
        matching_own_ids = {kind: set() for kind in relation_kinds}
        matching_parent_ids = {kind: set() for kind in relation_kinds}
        parent_by_child = {kind: {} for kind in relation_kinds}
        children_by_parent = {kind: {} for kind in relation_kinds}
        row_keys = {}

        def add_child(kind, parent_id, child_id):
            if not parent_id or not child_id:
                return
            parent_by_child[kind][child_id] = parent_id
            children_by_parent[kind].setdefault(parent_id, set()).add(child_id)

        for row in rows:
            keys = self._export_row_keys(row)
            row_keys[row] = keys
            for kind in relation_kinds:
                add_child(kind, keys['parent'][kind], keys['own'][kind])

            haystack = self._normalize_search_text(row.text_content())
            matches = needle in haystack
            matching_rows[row] = matches
            if not matches:
                continue
            for kind in relation_kinds:
                if keys['own'][kind]:
                    matching_own_ids[kind].add(keys['own'][kind])
                if keys['parent'][kind]:
                    matching_parent_ids[kind].add(keys['parent'][kind])

        for kind in relation_kinds:
            descendants = list(matching_own_ids[kind])
            for item_id in descendants:
                for child_id in children_by_parent[kind].get(item_id, set()):
                    if child_id not in matching_own_ids[kind]:
                        matching_own_ids[kind].add(child_id)
                        descendants.append(child_id)

            ancestors = list(matching_parent_ids[kind])
            for item_id in ancestors:
                parent_id = parent_by_child[kind].get(item_id)
                if parent_id and parent_id not in matching_parent_ids[kind]:
                    matching_parent_ids[kind].add(parent_id)
                    ancestors.append(parent_id)

        for row in rows:
            keys = row_keys[row]
            visible = matching_rows.get(row) or any(
                (keys['parent'][kind] and keys['parent'][kind] in matching_own_ids[kind])
                or (keys['own'][kind] and keys['own'][kind] in matching_own_ids[kind])
                or (keys['own'][kind] and keys['own'][kind] in matching_parent_ids[kind])
                for kind in relation_kinds
            )
            if not visible:
                parent = row.getparent()
                if parent is not None:
                    parent.remove(row)

        return lxml.html.tostring(root, encoding='unicode')

    def _decode_html(self, html_content):
        if isinstance(html_content, bytes):
            return html_content.decode('utf-8', errors='replace')
        return html_content or ''

    def _move_currency_symbol_after_amount(self, html_content):
        root = lxml.html.fromstring(self._decode_html(html_content))
        currency_before_pattern = re.compile(r'\b(SR|ر\.س|﷼)\s+(-?)(\d[\d,]*(?:\.\d+)?)(-?)')
        amount_before_pattern = re.compile(r'(-?)(\d[\d,]*(?:\.\d+)?)(-?)\s+(SR|ر\.س|﷼)')

        def swap(value):
            value = value or ''

            def currency_before(match):
                currency, leading_sign, amount, trailing_sign = match.groups()
                sign = '-' if leading_sign or trailing_sign else ''
                return '%s%s %s' % (sign, amount, currency)

            def amount_before(match):
                leading_sign, amount, trailing_sign, currency = match.groups()
                sign = '-' if leading_sign or trailing_sign else ''
                return '%s%s %s' % (sign, amount, currency)

            return amount_before_pattern.sub(
                amount_before,
                currency_before_pattern.sub(currency_before, value),
            )

        for node in root.iter():
            if node.text:
                node.text = swap(node.text)
            if node.tail:
                node.tail = swap(node.tail)
        return lxml.html.tostring(root, encoding='unicode')

    def _strip_report_action_nodes(self, html_content):
        root = lxml.html.fromstring(self._decode_html(html_content))
        drop_xpaths = [
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_account_row_tools ')]",
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_account_action_dropdown ')]",
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_account_action_journal ')]",
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_partner_actions ')]",
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_partner_action_item ')]",
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_aged_partner_actions ')]",
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_aged_partner_action_item ')]",
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_pl_line_tools ')]",
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_pl_line_action_dropdown ')]",
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_pl_line_action_item ')]",
            ".//button[@data-action]",
        ]
        for xpath in drop_xpaths:
            for node in root.xpath(xpath):
                parent = node.getparent()
                if parent is not None:
                    parent.remove(node)
        return lxml.html.tostring(root, encoding='unicode')

    def _strip_export_only_nodes(self, root):
        drop_xpaths = [
            './/script',
            './/style',
            './/button',
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_account_row_tools ')]",
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_account_action_dropdown ')]",
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_preview_hidden_search ')]",
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_acc_financial_folded_child ')]",
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_gl_folded_child ')]",
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_pl_folded_child ')]",
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_aged_folded_child ')]",
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_tb_folded_child ')]",
        ]
        for xpath in drop_xpaths:
            for node in root.xpath(xpath):
                parent = node.getparent()
                if parent is not None:
                    parent.remove(node)
        for node in root.xpath('//*[@style]'):
            style = (node.get('style') or '').replace(' ', '').lower()
            if 'display:none' in style or 'visibility:hidden' in style:
                parent = node.getparent()
                if parent is not None:
                    parent.remove(node)

    def _is_total_row(self, row):
        row_class = row.get('class') or ''
        row_style = (row.get('style') or '').replace(' ', '').lower()
        return (
            'o_acc_financial_section' in row_class
            or 'o_acc_financial_total' in row_class
            or 'o_total_row' in row_class
            or 'font-weight:bold' in row_style
        )

    def _is_group_row(self, row):
        return 'o_acc_financial_group' in (row.get('class') or '')

    def _is_negative_cell(self, cell, text):
        cell_class = cell.get('class') or ''
        return 'o_acc_financial_negative' in cell_class or text.endswith('-') or text.startswith('-')

    def _is_muted_cell(self, cell):
        cell_class = cell.get('class') or ''
        return 'o_acc_financial_muted' in cell_class

    def _numeric_cell_value(self, cell, text):
        """Return a real spreadsheet number for amount cells, never for labels/codes."""
        cell_class = cell.get('class') or ''
        numeric_classes = (
            'text-end', 'o_value_col', 'o_period_col', 'o_acc_financial_amount',
            'o_acc_financial_metric', 'number', 'amount',
        )
        if not any(css_class in cell_class for css_class in numeric_classes):
            return None
        normalized = text.translate(str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')).strip()
        negative = normalized.startswith('(') and normalized.endswith(')')
        if normalized.endswith('-') or re.search(r'\d(?:\.\d+)?-\s*(?:SR|ر\.س|﷼)?$', normalized):
            negative = True
        match = re.search(r'-?\d[\d,]*(?:\.\d+)?', normalized)
        if not match:
            return None
        value = float(match.group(0).replace(',', ''))
        return -abs(value) if negative else value

    def _write_html_table_to_sheet(self, workbook, sheet, table, start_row, formats):
        occupied = {}
        max_col = 0
        col_widths = {}
        row_idx = start_row
        for html_row in table.xpath('.//tr'):
            cells = html_row.xpath('./th|./td')
            if not cells:
                continue
            sheet.set_row(row_idx, 24)
            col_idx = 0
            is_header = any(cell.tag.lower() == 'th' for cell in cells)
            is_total = self._is_total_row(html_row)
            is_group = self._is_group_row(html_row)
            for cell in cells:
                while occupied.get((row_idx, col_idx)):
                    col_idx += 1
                text = self._normalize_cell_text(cell.text_content())
                colspan = int(cell.get('colspan') or 1)
                rowspan = int(cell.get('rowspan') or 1)
                number_value = self._numeric_cell_value(cell, text)
                fmt = formats['number'] if number_value is not None else formats['cell']
                if is_header:
                    fmt = formats['header']
                elif is_total:
                    if number_value is not None:
                        fmt = formats['total_number_negative'] if number_value < 0 else formats['total_number']
                    else:
                        fmt = formats['total_negative'] if self._is_negative_cell(cell, text) else formats['total']
                elif is_group:
                    if number_value is not None:
                        fmt = formats['group_number_negative'] if number_value < 0 else formats['group_number']
                    else:
                        fmt = formats['group_negative'] if self._is_negative_cell(cell, text) else formats['group']
                elif self._is_negative_cell(cell, text):
                    fmt = formats['number_negative'] if number_value is not None else formats['negative']
                elif self._is_muted_cell(cell):
                    fmt = formats['number_muted'] if number_value is not None else formats['muted']
                value = number_value if number_value is not None and not is_header else text
                if colspan > 1 or rowspan > 1:
                    sheet.merge_range(
                        row_idx,
                        col_idx,
                        row_idx + rowspan - 1,
                        col_idx + colspan - 1,
                        value,
                        fmt,
                    )
                else:
                    sheet.write(row_idx, col_idx, value, fmt)
                display_width = max(10, min(42, int(len(text) * 1.15) + 4))
                for col_offset in range(colspan):
                    target_col = col_idx + col_offset
                    col_widths[target_col] = max(col_widths.get(target_col, 0), display_width)
                for row_offset in range(rowspan):
                    for col_offset in range(colspan):
                        occupied[(row_idx + row_offset, col_idx + col_offset)] = True
                col_idx += colspan
                max_col = max(max_col, col_idx - 1)
            row_idx += 1
        return row_idx, max_col, col_widths

    def _build_xlsx_from_html(self, workbook, report_label, html_content):
        root = lxml.html.fromstring(self._decode_html(html_content))
        self._strip_export_only_nodes(root)
        tables = root.xpath('//table[.//tr]')
        if not tables:
            return False

        sheet = workbook.add_worksheet(self._safe_sheet_name(report_label))
        sheet.right_to_left()
        sheet.hide_gridlines(2)
        sheet.set_default_row(22)
        sheet.set_margins(left=0.25, right=0.25, top=0.3, bottom=0.3)
        sheet.fit_to_pages(1, 0)
        sheet.center_horizontally()

        formats = {
            'title': workbook.add_format({
                'bold': True, 'font_name': 'DejaVu Sans', 'font_size': 13,
                'align': 'right', 'valign': 'vcenter',
            }),
            'cell': workbook.add_format({
                'font_name': 'DejaVu Sans', 'font_size': 10,
                'align': 'right', 'valign': 'vcenter', 'border': 1,
                'border_color': '#D9DEE7', 'text_wrap': True,
            }),
            'number': workbook.add_format({
                'font_name': 'DejaVu Sans', 'font_size': 10,
                'align': 'left', 'valign': 'vcenter', 'border': 1,
                'border_color': '#D9DEE7',
                'num_format': '#,##0.00;[Red]-#,##0.00',
            }),
            'header': workbook.add_format({
                'bold': True, 'font_name': 'DejaVu Sans', 'font_size': 10,
                'align': 'center', 'valign': 'vcenter', 'border': 1,
                'border_color': '#C8D0DB', 'bg_color': '#EEF2F7',
            }),
            'total': workbook.add_format({
                'bold': True, 'font_name': 'DejaVu Sans', 'font_size': 10,
                'align': 'right', 'valign': 'vcenter', 'bg_color': '#D8DADD',
                'border': 1, 'border_color': '#C8D0DB',
            }),
            'total_negative': workbook.add_format({
                'bold': True, 'font_name': 'DejaVu Sans', 'font_size': 10,
                'align': 'right', 'valign': 'vcenter', 'bg_color': '#D8DADD',
                'font_color': '#E02020', 'border': 1, 'border_color': '#C8D0DB',
            }),
            'total_number': workbook.add_format({
                'bold': True, 'font_name': 'DejaVu Sans', 'font_size': 10,
                'align': 'left', 'valign': 'vcenter', 'bg_color': '#D8DADD',
                'border': 1, 'border_color': '#C8D0DB', 'num_format': '#,##0.00;[Red]-#,##0.00',
            }),
            'total_number_negative': workbook.add_format({
                'bold': True, 'font_name': 'DejaVu Sans', 'font_size': 10,
                'align': 'left', 'valign': 'vcenter', 'bg_color': '#D8DADD',
                'font_color': '#E02020', 'border': 1, 'border_color': '#C8D0DB',
                'num_format': '#,##0.00;[Red]-#,##0.00',
            }),
            'group': workbook.add_format({
                'bold': True, 'font_name': 'DejaVu Sans', 'font_size': 10,
                'align': 'right', 'valign': 'vcenter', 'border': 1,
                'border_color': '#D9DEE7', 'bg_color': '#F6F8FB',
            }),
            'group_negative': workbook.add_format({
                'bold': True, 'font_name': 'DejaVu Sans', 'font_size': 10,
                'align': 'right', 'valign': 'vcenter', 'font_color': '#E02020',
                'border': 1, 'border_color': '#D9DEE7', 'bg_color': '#F6F8FB',
            }),
            'group_number': workbook.add_format({
                'bold': True, 'font_name': 'DejaVu Sans', 'font_size': 10,
                'align': 'left', 'valign': 'vcenter', 'border': 1,
                'border_color': '#D9DEE7', 'bg_color': '#F6F8FB',
                'num_format': '#,##0.00;[Red]-#,##0.00',
            }),
            'group_number_negative': workbook.add_format({
                'bold': True, 'font_name': 'DejaVu Sans', 'font_size': 10,
                'align': 'left', 'valign': 'vcenter', 'font_color': '#E02020',
                'border': 1, 'border_color': '#D9DEE7', 'bg_color': '#F6F8FB',
                'num_format': '#,##0.00;[Red]-#,##0.00',
            }),
            'negative': workbook.add_format({
                'font_name': 'DejaVu Sans', 'font_size': 10,
                'align': 'right', 'valign': 'vcenter', 'font_color': '#E02020',
                'border': 1, 'border_color': '#D9DEE7', 'text_wrap': True,
            }),
            'number_negative': workbook.add_format({
                'font_name': 'DejaVu Sans', 'font_size': 10,
                'align': 'left', 'valign': 'vcenter', 'font_color': '#E02020',
                'border': 1, 'border_color': '#D9DEE7', 'num_format': '#,##0.00;[Red]-#,##0.00',
            }),
            'muted': workbook.add_format({
                'font_name': 'DejaVu Sans', 'font_size': 10,
                'align': 'right', 'valign': 'vcenter', 'font_color': '#C3CAD3',
                'border': 1, 'border_color': '#D9DEE7', 'text_wrap': True,
            }),
            'number_muted': workbook.add_format({
                'font_name': 'DejaVu Sans', 'font_size': 10,
                'align': 'left', 'valign': 'vcenter', 'font_color': '#C3CAD3',
                'border': 1, 'border_color': '#D9DEE7', 'num_format': '#,##0.00;[Red]-#,##0.00',
            }),
        }

        row_idx = 0
        period = root.xpath(".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_acc_financial_period ')]")
        balance_label = root.xpath(".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_acc_financial_balance_label ')]")
        analytic_selection = root.xpath(".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_report_analytic_selection ')]")
        lead_texts = [self._normalize_cell_text(node.text_content()) for node in period]
        lead_texts += [self._normalize_cell_text(node.text_content()) for node in balance_label]
        lead_texts += [self._normalize_cell_text(node.text_content()) for node in analytic_selection[:1]]
        for text in [text for text in lead_texts if text]:
            sheet.write(row_idx, 0, text, formats['title'])
            row_idx += 1
        if lead_texts:
            row_idx += 1

        max_col = 0
        all_col_widths = {}
        first_table_row = row_idx
        for table in tables:
            row_idx, table_max_col, col_widths = self._write_html_table_to_sheet(workbook, sheet, table, row_idx, formats)
            max_col = max(max_col, table_max_col)
            for col_idx, width in col_widths.items():
                all_col_widths[col_idx] = max(all_col_widths.get(col_idx, 0), width)
            row_idx += 1

        for col_idx in range(max_col + 1):
            width = all_col_widths.get(col_idx, 14)
            sheet.set_column(col_idx, col_idx, min(42, max(12, width)))
        if first_table_row < row_idx:
            sheet.freeze_panes(first_table_row + 1, 0)
            sheet.repeat_rows(first_table_row, first_table_row)
            sheet.autofilter(first_table_row, 0, max(first_table_row, row_idx - 2), max_col)
        if max_col >= 5:
            sheet.set_landscape()
        else:
            sheet.set_portrait()
        sheet.print_area(0, 0, max(0, row_idx - 1), max_col)
        return True

    def _build_xlsx(self, report_name, report_label, report_values, html_content=None):
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        if html_content and self._build_xlsx_from_html(workbook, report_label, html_content):
            workbook.close()
            return output.getvalue()

        money_format = workbook.add_format({'num_format': '#,##0.00'})
        bold = workbook.add_format({'bold': True})

        if report_name == 'accounting_pdf_reports.report_trialbalance':
            sheet = workbook.add_worksheet('ميزان المراجعة')
            headers = ['الرصيد النهائي', 'الدائن', 'المدين', 'الرصيد الافتتاحي', 'الحساب']
            sheet.write_row(0, 0, headers, bold)
            for row_idx, account in enumerate(report_values.get('Accounts', []), start=1):
                sheet.write_number(row_idx, 0, account.get('closing_balance') or 0.0, money_format)
                sheet.write_number(row_idx, 1, account.get('credit') or 0.0, money_format)
                sheet.write_number(row_idx, 2, account.get('debit') or 0.0, money_format)
                sheet.write_number(row_idx, 3, account.get('opening_balance') or 0.0, money_format)
                sheet.write(row_idx, 4, account.get('display_name') or account.get('name'))

        elif report_name == 'accounting_pdf_reports.report_financial':
            sheet = workbook.add_worksheet('التقرير المالي')
            comparison_order = ((report_values.get('data') or {}).get('comparison_order')) or 'descending'
            comparison_label = ((report_values.get('data') or {}).get('label_filter')) or 'المقارنة'
            if comparison_order == 'ascending':
                headers = ['الاسم', 'النوع', 'المدين', 'الدائن', comparison_label, 'الرصيد']
            else:
                headers = ['الاسم', 'النوع', 'المدين', 'الدائن', 'الرصيد', comparison_label]
            sheet.write_row(0, 0, headers, bold)
            for row_idx, line in enumerate(report_values.get('get_account_lines', []), start=1):
                sheet.write(row_idx, 0, line.get('name'))
                sheet.write(row_idx, 1, line.get('type'))
                sheet.write_number(row_idx, 2, line.get('debit') or 0.0, money_format)
                sheet.write_number(row_idx, 3, line.get('credit') or 0.0, money_format)
                if comparison_order == 'ascending':
                    sheet.write_number(row_idx, 4, line.get('balance_cmp') or 0.0, money_format)
                    sheet.write_number(row_idx, 5, line.get('balance') or 0.0, money_format)
                else:
                    sheet.write_number(row_idx, 4, line.get('balance') or 0.0, money_format)
                    sheet.write_number(row_idx, 5, line.get('balance_cmp') or 0.0, money_format)

        elif report_name == 'accounting_pdf_reports.report_general_ledger':
            sheet = workbook.add_worksheet('General Ledger')
            headers = ['Account', 'Code', 'Debit', 'Credit', 'Balance', 'Line Date', 'Partner', 'Journal', 'Label', 'Move']
            sheet.write_row(0, 0, headers, bold)
            row_idx = 1
            for account in report_values.get('Accounts', []):
                sheet.write(row_idx, 0, account.get('name'))
                sheet.write(row_idx, 1, account.get('code'))
                sheet.write_number(row_idx, 2, account.get('debit') or 0.0, money_format)
                sheet.write_number(row_idx, 3, account.get('credit') or 0.0, money_format)
                sheet.write_number(row_idx, 4, account.get('balance') or 0.0, money_format)
                row_idx += 1
                for line in account.get('move_lines', []):
                    sheet.write(row_idx, 0, '')
                    sheet.write(row_idx, 1, '')
                    sheet.write_number(row_idx, 2, line.get('debit') or 0.0, money_format)
                    sheet.write_number(row_idx, 3, line.get('credit') or 0.0, money_format)
                    sheet.write_number(row_idx, 4, line.get('balance') or 0.0, money_format)
                    sheet.write(row_idx, 5, str(line.get('ldate') or ''))
                    sheet.write(row_idx, 6, line.get('partner_name'))
                    sheet.write(row_idx, 7, line.get('lcode'))
                    sheet.write(row_idx, 8, line.get('lname'))
                    sheet.write(row_idx, 9, line.get('move_name'))
                    row_idx += 1

        elif report_name == 'accounting_pdf_reports.report_partnerledger':
            sheet = workbook.add_worksheet('Partner Ledger')
            headers = ['Partner', 'Date', 'Journal', 'Account', 'Label', 'Debit', 'Credit', 'Balance']
            sheet.write_row(0, 0, headers, bold)
            row_idx = 1
            for partner in report_values.get('docs', []):
                lines = report_values['lines'](report_values['data']['form']['target_move'], partner.id, report_values['data']['form'].get('sortby', 'date'), report_values)
                for line in lines:
                    sheet.write(row_idx, 0, partner.name)
                    sheet.write(row_idx, 1, str(line.get('date') or ''))
                    sheet.write(row_idx, 2, line.get('lcode'))
                    sheet.write(row_idx, 3, line.get('a_code'))
                    sheet.write(row_idx, 4, line.get('lname'))
                    sheet.write_number(row_idx, 5, line.get('debit') or 0.0, money_format)
                    sheet.write_number(row_idx, 6, line.get('credit') or 0.0, money_format)
                    sheet.write_number(row_idx, 7, line.get('progress') or 0.0, money_format)
                    row_idx += 1

        elif report_name == 'accounting_pdf_reports.report_agedpartnerbalance':
            sheet = workbook.add_worksheet('Aged Partner Balance')
            headers = ['Partner', 'Not Due', '1-30', '31-60', '61-90', '91-120', '+120', 'Total']
            sheet.write_row(0, 0, headers, bold)
            row_idx = 1
            for partner in report_values.get('get_partner_lines', []):
                sheet.write(row_idx, 0, partner.get('name'))
                sheet.write_number(row_idx, 1, partner.get('direction') or 0.0, money_format)
                for idx in range(5):
                    sheet.write_number(row_idx, 2 + idx, partner.get(str(idx)) or 0.0, money_format)
                sheet.write_number(row_idx, 7, partner.get('total') or 0.0, money_format)
                row_idx += 1

        elif report_name == 'accounting_pdf_reports.report_tax':
            sheet = workbook.add_worksheet('Tax Report')
            headers = ['Tax', 'Type', 'Group', 'Net Amount', 'Tax Amount']
            sheet.write_row(0, 0, headers, bold)
            row_idx = 1
            for group, taxes in report_values.get('lines', {}).items():
                for tax in taxes:
                    sheet.write(row_idx, 0, tax.get('name'))
                    sheet.write(row_idx, 1, tax.get('type'))
                    sheet.write(row_idx, 2, group)
                    sheet.write_number(row_idx, 3, tax.get('net') or 0.0, money_format)
                    sheet.write_number(row_idx, 4, tax.get('tax') or 0.0, money_format)
                    row_idx += 1

        elif report_name == 'accounting_pdf_reports.report_journal':
            sheet = workbook.add_worksheet('Journals Audit')
            headers = ['Journal', 'Date', 'Account', 'Reference', 'Label', 'Debit', 'Credit']
            sheet.write_row(0, 0, headers, bold)
            row_idx = 1
            for journal in report_values.get('docs', []):
                lines = report_values['lines'](report_values['data']['form'].get('target_move', 'all'), journal.id, report_values['data']['form'].get('sort_selection', 'date'), report_values)
                for line in lines:
                    sheet.write(row_idx, 0, journal.name)
                    sheet.write(row_idx, 1, str(line.get('ldate') or ''))
                    sheet.write(row_idx, 2, line.get('a_code'))
                    sheet.write(row_idx, 3, line.get('lref'))
                    sheet.write(row_idx, 4, line.get('lname'))
                    sheet.write_number(row_idx, 5, line.get('debit') or 0.0, money_format)
                    sheet.write_number(row_idx, 6, line.get('credit') or 0.0, money_format)
                    row_idx += 1

        elif report_name == 'accounting_pdf_reports.report_journal_entries':
            sheet = workbook.add_worksheet('Journal Entries')
            headers = ['Journal Entry', 'Journal', 'Date', 'Partner', 'Reference', 'Account', 'Analytic Account', 'Debit', 'Credit']
            sheet.write_row(0, 0, headers, bold)
            row_idx = 1
            for entry in report_values.get('docs', []):
                for line in entry.line_ids:
                    sheet.write(row_idx, 0, entry.name)
                    sheet.write(row_idx, 1, entry.journal_id.name)
                    sheet.write(row_idx, 2, str(line.date or ''))
                    sheet.write(row_idx, 3, line.partner_id.display_name or '')
                    sheet.write(row_idx, 4, line.ref or '')
                    sheet.write(row_idx, 5, line.account_id.name or '')
                    sheet.write(row_idx, 6, '')
                    sheet.write_number(row_idx, 7, line.debit or 0.0, money_format)
                    sheet.write_number(row_idx, 8, line.credit or 0.0, money_format)
                    row_idx += 1

        elif report_name == 'om_account_daily_reports.report_daybook':
            sheet = workbook.add_worksheet('Day Book')
            headers = ['Date', 'Journal', 'Partner', 'Reference', 'Move', 'Entry Label', 'Debit', 'Credit', 'Balance']
            sheet.write_row(0, 0, headers, bold)
            row_idx = 1
            for day in report_values.get('Accounts', []):
                sheet.write(row_idx, 0, str(day.get('date') or ''))
                sheet.write(row_idx, 5, 'Total', bold)
                sheet.write_number(row_idx, 6, day.get('debit') or 0.0, money_format)
                sheet.write_number(row_idx, 7, day.get('credit') or 0.0, money_format)
                sheet.write_number(row_idx, 8, day.get('balance') or 0.0, money_format)
                row_idx += 1
                for line in day.get('move_lines', []):
                    sheet.write(row_idx, 0, str(line.get('ldate') or ''))
                    sheet.write(row_idx, 1, line.get('lcode') or '')
                    sheet.write(row_idx, 2, line.get('lpartner_id') or '')
                    sheet.write(row_idx, 3, line.get('lref') or '')
                    sheet.write(row_idx, 4, line.get('move_name') or '')
                    sheet.write(row_idx, 5, line.get('lname') or '')
                    sheet.write_number(row_idx, 6, line.get('debit') or 0.0, money_format)
                    sheet.write_number(row_idx, 7, line.get('credit') or 0.0, money_format)
                    sheet.write_number(row_idx, 8, line.get('balance') or 0.0, money_format)
                    row_idx += 1

        elif report_name in ('om_account_daily_reports.report_cashbook', 'om_account_daily_reports.report_bankbook'):
            sheet = workbook.add_worksheet('Cash Book' if report_name.endswith('cashbook') else 'Bank Book')
            headers = ['Account', 'Code', 'Date', 'Journal', 'Partner', 'Reference', 'Move', 'Entry Label', 'Debit', 'Credit', 'Balance']
            sheet.write_row(0, 0, headers, bold)
            row_idx = 1
            for account in report_values.get('Accounts', []):
                sheet.write(row_idx, 0, account.get('name') or '', bold)
                sheet.write(row_idx, 1, account.get('code') or '', bold)
                sheet.write_number(row_idx, 8, account.get('debit') or 0.0, money_format)
                sheet.write_number(row_idx, 9, account.get('credit') or 0.0, money_format)
                sheet.write_number(row_idx, 10, account.get('balance') or 0.0, money_format)
                row_idx += 1
                for line in account.get('move_lines', []):
                    sheet.write(row_idx, 0, account.get('name') or '')
                    sheet.write(row_idx, 1, account.get('code') or '')
                    sheet.write(row_idx, 2, str(line.get('ldate') or ''))
                    sheet.write(row_idx, 3, line.get('lcode') or '')
                    sheet.write(row_idx, 4, line.get('partner_name') or line.get('lpartner_id') or '')
                    sheet.write(row_idx, 5, line.get('lref') or '')
                    sheet.write(row_idx, 6, line.get('move_name') or '')
                    sheet.write(row_idx, 7, line.get('lname') or '')
                    sheet.write_number(row_idx, 8, line.get('debit') or 0.0, money_format)
                    sheet.write_number(row_idx, 9, line.get('credit') or 0.0, money_format)
                    sheet.write_number(row_idx, 10, line.get('balance') or 0.0, money_format)
                    row_idx += 1

        else:
            sheet = workbook.add_worksheet('Report')
            sheet.write(0, 0, report_label, bold)

        workbook.close()
        return output.getvalue()
