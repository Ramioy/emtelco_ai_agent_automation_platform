"""Server-rendered HTML; the operator-facing copy is Spanish on purpose, the code is not."""
from html import escape

ORDER_STATUSES = (
    "PENDING",
    "PROCESSING",
    "DISPATCHED",
    "IN_TRANSIT",
    "DELIVERED",
    "CANCELLED",
)

WARRANTY_STATES = (("reinstate", "VIGENTE"), ("terminate", "VENCIDA"))

TICKET_STATUS_LABELS = {
    "pending_agent": "PENDIENTE",
    "in_progress": "EN CURSO",
    "resolved": "RESUELTO",
}

TICKET_STATUS_TONES = {"pending_agent": "amber", "in_progress": "blue", "resolved": "green"}

PRIORITY_TONES = {"high": "red", "medium": "amber", "low": "slate"}

# The microservice answers in English, as all code does; the console speaks to a Spanish
# operator, so its refusals are translated here rather than shown raw.
REFUSAL_MESSAGES = {
    "human_review_required": (
        "Este ticket es de riesgo de seguridad: alguien tiene que tomarlo antes de poder "
        "cerrarlo. Usa Tomar y despues Resolver."
    ),
    "resolution_note_required": "Para cerrar un ticket hace falta la nota de como se resolvio.",
    "assignee_required": "Para tomar un ticket hace falta el nombre de quien lo atiende.",
    "invalid_transition": "Ese ticket ya no puede pasar a ese estado.",
    "not_found": "Ese ticket ya no existe.",
}

# Stored reasons are English and repeat what the Origen badge says; the prefix goes at the edge.
REASON_PREFIXES = (
    "Safety risk reported in a warranty claim: ",
    "Warranty claim: ",
)

# The three ways a ticket is born; only the safety one may not be closed without being taken.
TICKET_ORIGIN_LABELS = {
    "agent_request": ("slate", "PEDIDO DEL CLIENTE"),
    "warranty_claim": ("blue", "RECLAMO DE GARANTIA"),
    "safety_risk": ("red", "RIESGO DE SEGURIDAD"),
}

STATUS_TONES = {
    "PENDING": "slate",
    "PROCESSING": "blue",
    "DISPATCHED": "violet",
    "IN_TRANSIT": "amber",
    "DELIVERED": "green",
    "CANCELLED": "red",
}

STYLES = """
:root {
  --bg: #f2f4f7;
  --surface: #ffffff;
  --border: #dde1e8;
  --text: #161d26;
  --muted: #667085;
  --accent: #2f4fd0;
  --shadow: 0 1px 2px rgba(16, 24, 40, .06), 0 1px 3px rgba(16, 24, 40, .08);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 32px 24px 64px;
  background: var(--bg);
  color: var(--text);
  font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial,
        sans-serif;
  -webkit-font-smoothing: antialiased;
}
.page { max-width: 1240px; margin: 0 auto; }
header.masthead {
  display: flex; align-items: baseline; justify-content: space-between;
  flex-wrap: wrap; gap: 12px; margin-bottom: 28px;
}
h1 { font-size: 26px; letter-spacing: -.01em; margin: 0 0 4px; }
.subtitle { color: var(--muted); margin: 0; font-size: 15px; }
.reload { color: var(--accent); font-size: 14px; text-decoration: none; font-weight: 600; }
.reload:hover { text-decoration: underline; }
.stamp { color: var(--muted); font-size: 13px; font-variant-numeric: tabular-nums; }
.masthead .right { text-align: right; }
.banner {
  border-radius: 10px; padding: 14px 18px; margin-bottom: 24px; font-size: 15px;
  border: 1px solid; box-shadow: var(--shadow);
}
.banner.ok { background: #eaf7ee; border-color: #b8e0c4; color: #17552c; }
.banner.bad { background: #fdecec; border-color: #f2c0c0; color: #7a1d1d; }
.banner strong { font-weight: 700; }
section { margin-bottom: 40px; }
h2 { font-size: 19px; margin: 0 0 4px; letter-spacing: -.01em; }
.hint { color: var(--muted); font-size: 14px; margin: 0 0 14px; }
.card {
  background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
  box-shadow: var(--shadow); overflow-x: auto;
}
table { border-collapse: collapse; width: 100%; font-size: 15px; }
th {
  text-align: left; font-size: 12px; text-transform: uppercase; letter-spacing: .06em;
  color: var(--muted); font-weight: 700; padding: 14px 18px; border-bottom: 1px solid var(--border);
  background: #fafbfc; white-space: nowrap;
}
td { padding: 16px 18px; border-bottom: 1px solid #eef0f4; vertical-align: middle; }
tr:last-child td { border-bottom: none; }
tr.touched td { background: #fffbe8; }
.id { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 14px; }
.product { font-weight: 600; }
.brand { display: block; color: var(--muted); font-weight: 400; font-size: 13px; }
.address { max-width: 240px; color: var(--muted); font-size: 14px; }
.date { font-variant-numeric: tabular-nums; white-space: nowrap; }
.tag {
  display: inline-block; margin-left: 8px; padding: 2px 8px; border-radius: 999px;
  background: #fde9a9; color: #7a5a00; font-size: 11px; font-weight: 700;
  text-transform: uppercase; letter-spacing: .05em;
}
.badge {
  display: inline-block; padding: 5px 11px; border-radius: 999px; font-size: 12.5px;
  font-weight: 700; letter-spacing: .04em; white-space: nowrap; border: 1px solid;
}
.badge.slate  { background: #eef1f5; border-color: #d3d9e2; color: #3d4757; }
.badge.blue   { background: #e7f0fe; border-color: #c2d8fb; color: #14428f; }
.badge.violet { background: #efeafd; border-color: #d6c9f8; color: #4a2b93; }
.badge.amber  { background: #fdf1dc; border-color: #f4dcae; color: #7a4d06; }
.badge.green  { background: #e6f6ec; border-color: #bce3c9; color: #17552c; }
.badge.red    { background: #fdeaea; border-color: #f4c5c5; color: #8a1f1f; }
tr.safety td { background: #fff7f6; }
tr.safety.touched td { background: #fff4e0; }
.reason { max-width: 320px; font-size: 14px; }
.note { display: block; color: var(--muted); font-size: 13px; margin-top: 3px; }
.locked { color: #8a1f1f; font-size: 12.5px; font-weight: 600; }
.editor input.who { width: 118px; }
.editor input.why { width: 190px; }
.editor { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 0; }
.editor input {
  font: inherit; font-size: 13px; padding: 5px 8px; border-radius: 7px;
  border: 1px solid var(--border); background: var(--surface); color: var(--text);
  font-variant-numeric: tabular-nums;
}
.editor input.months { width: 66px; text-align: right; }
.editor .unit { color: var(--muted); font-size: 13px; }
.editor button {
  font: inherit; font-size: 12.5px; font-weight: 600; letter-spacing: .03em;
  padding: 6px 11px; border-radius: 7px; border: 1px solid var(--border);
  background: var(--surface); color: #3d4757; cursor: pointer;
}
.editor button:hover { border-color: var(--accent); color: var(--accent); background: #f6f8ff; }
.switcher { display: flex; flex-wrap: wrap; gap: 6px; margin: 0; }
.switcher button {
  font: inherit; font-size: 12.5px; font-weight: 600; letter-spacing: .03em;
  padding: 6px 11px; border-radius: 7px; border: 1px solid var(--border);
  background: var(--surface); color: #3d4757; cursor: pointer;
}
.switcher button:hover { border-color: var(--accent); color: var(--accent); background: #f6f8ff; }
.switcher .current {
  display: inline-block; font-size: 12.5px; font-weight: 700; letter-spacing: .03em;
  padding: 6px 11px; border-radius: 7px; border: 1px dashed #c3cad6; color: #98a2b3;
  background: #f7f8fa;
}
footer { color: var(--muted); font-size: 13px; border-top: 1px solid var(--border); padding-top: 16px; }
footer code { background: #e9ecf1; padding: 1px 6px; border-radius: 4px; font-size: 12.5px; }
"""


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html>\n<html lang=\"es\">\n<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(title)}</title>\n"
        f"<style>{STYLES}</style>\n"
        "</head>\n<body>\n"
        f'<div class="page">{body}</div>\n'
        "</body>\n</html>\n"
    )


def _money(value) -> str:
    if value is None:
        return ""
    return "$ " + f"{value:,}".replace(",", ".")


def _product_cell(details: list[dict], fallback_ids: list[str]) -> str:
    if not details:
        return f'<span class="id">{escape(", ".join(fallback_ids))}</span>'
    parts = []
    for detail in details:
        name = detail.get("name")
        if name is None:
            parts.append(
                f'<span class="id">{escape(detail["product_id"])}</span>'
                '<span class="brand">fuera de catalogo</span>'
            )
            continue
        brand = escape(detail.get("brand") or "")
        price = _money(detail.get("price"))
        gloss = " &middot; ".join(part for part in (brand, price) if part)
        parts.append(f'{escape(name)}<span class="brand">{gloss}</span>')
    return "".join(parts)


def _status_badge(status: str) -> str:
    tone = STATUS_TONES.get(status, "slate")
    return f'<span class="badge {tone}">{escape(status)}</span>'


def _status_switcher(order_id: str, current: str) -> str:
    buttons = []
    for status in ORDER_STATUSES:
        if status == current:
            buttons.append(f'<span class="current">{escape(status)}</span>')
        else:
            action = f"/orders/{escape(order_id)}/status/{escape(status)}"
            buttons.append(f'<button formaction="{action}">{escape(status)}</button>')
    return (
        f'<form class="switcher" method="post" '
        f'action="/orders/{escape(order_id)}/status/{escape(current)}">'
        + "".join(buttons)
        + "</form>"
    )


def _orders_section(orders: list[dict], names: dict[str, str], touched: str | None) -> str:
    rows = []
    for order in orders:
        order_id = order["order_id"]
        client_id = order["client_id"]
        client = names.get(client_id, client_id)
        tag = '<span class="tag">actualizado</span>' if order_id == touched else ""
        rows.append(
            f'<tr class="{"touched" if order_id == touched else ""}">'
            f'<td class="id">{escape(order_id)}{tag}</td>'
            f'<td>{escape(client)}<span class="brand id">{escape(client_id)}</span></td>'
            f'<td class="product">'
            f'{_product_cell(order.get("product_details", []), order.get("products", []))}</td>'
            f"<td>{_status_badge(order['status'])}</td>"
            f'<td class="address">{escape(order["delivery_address"])}</td>'
            f'<td class="date">{escape(order["estimated_delivery_date"])}</td>'
            f"<td>{_status_switcher(order_id, order['status'])}</td>"
            "</tr>"
        )
    return (
        "<section>"
        "<h2>Pedidos</h2>"
        '<p class="hint">Un clic cambia el estado. Despues pregunta de nuevo al agente en una '
        "conversacion nueva y la respuesta cambia con el.</p>"
        '<div class="card"><table><thead><tr>'
        "<th>Pedido</th><th>Cliente</th><th>Producto</th><th>Estado</th>"
        "<th>Direccion de entrega</th><th>Entrega estimada</th><th>Cambiar estado</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div></section>"
    )


def _coverage_editor(warranty_id: str, coverage_months: int, purchase_date: str) -> str:
    """Coverage and purchase date are the two inputs validity is computed from, so editing
    them here can stage any case the agent has to report, not only the two one-click ones."""
    return (
        f'<form class="editor" method="post" action="/warranties/{escape(warranty_id)}/edit">'
        '<input class="months" type="number" name="coverage_months" min="0" max="120" '
        f'value="{int(coverage_months)}" aria-label="Meses de cobertura">'
        '<span class="unit">meses desde</span>'
        f'<input type="date" name="purchase_date" value="{escape(purchase_date)}" '
        'aria-label="Fecha de compra">'
        "<button>Guardar</button></form>"
    )


def _validity_switcher(warranty_id: str, is_valid: bool) -> str:
    """Same two-state control as the order status switcher: the state the warranty is in shows
    as the inert pill, the other one as the button that takes it there."""
    current = WARRANTY_STATES[0] if is_valid else WARRANTY_STATES[1]
    buttons = []
    for path, label in WARRANTY_STATES:
        if (path, label) == current:
            buttons.append(f'<span class="current">{escape(label)}</span>')
        else:
            action = f"/warranties/{escape(warranty_id)}/{path}"
            buttons.append(f'<button formaction="{action}">{escape(label)}</button>')
    return (
        f'<form class="switcher" method="post" '
        f'action="/warranties/{escape(warranty_id)}/{current[0]}">'
        + "".join(buttons)
        + "</form>"
    )


def _warranty_row(warranty: dict, touched: str | None) -> str:
    warranty_id = warranty["warranty_id"]
    name = warranty.get("product_name") or warranty["product_id"]
    if warranty["is_valid"]:
        validity = (
            '<span class="badge green">VIGENTE</span>'
            f'<span class="brand">{warranty["months_remaining"]} meses restantes</span>'
        )
    else:
        validity = '<span class="badge red">VENCIDA</span>'
    editor = _coverage_editor(
        warranty_id, warranty["coverage_months"], warranty["purchase_date"]
    )
    action = _validity_switcher(warranty_id, warranty["is_valid"])
    tag = '<span class="tag">actualizado</span>' if warranty_id == touched else ""
    return (
        f'<tr class="{"touched" if warranty_id == touched else ""}">'
        f'<td class="id">{escape(warranty_id)}{tag}</td>'
        f'<td class="id">{escape(warranty["order_id"])}</td>'
        f'<td class="product">{escape(name)}'
        f'<span class="brand id">{escape(warranty["product_id"])}</span></td>'
        f"<td>{editor}</td>"
        f"<td>{validity}</td>"
        f"<td>{action}</td>"
        "</tr>"
    )


def _warranties_section(warranties: list[dict], touched: str | None) -> str:
    rows = "".join(_warranty_row(warranty, touched) for warranty in warranties)
    return (
        "<section>"
        "<h2>Garantias</h2>"
        '<p class="hint">Cada pedido nace con la garantia del producto. Vencer una deja ver la '
        'diferencia entre "vencida" y "no registrada", que son dos respuestas distintas del '
        "agente; volver a ponerla vigente extiende la cobertura un ano desde hoy, asi la "
        "demostracion se puede repetir. Los meses de cobertura y la fecha de compra tambien se "
        "pueden editar aqui: son los dos datos con los que se calcula la vigencia.</p>"
        '<div class="card"><table><thead><tr>'
        "<th>Garantia</th><th>Pedido</th><th>Producto</th><th>Cobertura</th>"
        "<th>Vigencia</th><th>Cambiar vigencia</th>"
        "</tr></thead><tbody>" + rows + "</tbody></table></div></section>"
    )


def _ticket_client_cell(ticket: dict, names: dict[str, str]) -> str:
    client_id = ticket.get("client_id")
    if not client_id:
        return '<span class="brand">sin identificar</span>'
    name = names.get(client_id, client_id)
    return f'{escape(name)}<span class="brand id">{escape(client_id)}</span>'


def _ticket_state_cell(ticket: dict) -> str:
    status = ticket["status"]
    tone = TICKET_STATUS_TONES.get(status, "slate")
    label = TICKET_STATUS_LABELS.get(status, status)
    parts = [f'<span class="badge {tone}">{escape(label)}</span>']
    if ticket.get("assignee"):
        parts.append(f'<span class="note">atiende {escape(ticket["assignee"])}</span>')
    if ticket.get("resolution_note"):
        parts.append(f'<span class="note">{escape(ticket["resolution_note"])}</span>')
    return "".join(parts)


def _ticket_actions(ticket: dict) -> str:
    """One form per row. A safety ticket in PENDIENTE is offered no way to close: the store
    refuses that transition, and the panel must not present a button that cannot work."""
    ticket_id = escape(ticket["ticket_id"])
    status = ticket["status"]
    safety = ticket.get("origin") == "safety_risk"
    assignee = escape(ticket.get("assignee") or "")
    fields = []
    buttons = []

    if status in ("pending_agent", "in_progress"):
        fields.append(
            '<input class="who" type="text" name="assignee" placeholder="quien atiende" '
            f'value="{assignee}" aria-label="Quien atiende">'
        )
    if status == "pending_agent":
        buttons.append(f'<button formaction="/tickets/{ticket_id}/in_progress">Tomar</button>')
    if status == "in_progress" or (status == "pending_agent" and not safety):
        fields.append(
            '<input class="why" type="text" name="resolution_note" '
            'placeholder="como se resolvio" aria-label="Nota de cierre">'
        )
        buttons.append(f'<button formaction="/tickets/{ticket_id}/resolved">Resolver</button>')
    if status == "resolved":
        buttons.append(f'<button formaction="/tickets/{ticket_id}/in_progress">Reabrir</button>')

    body = "".join(fields + buttons)
    if status == "pending_agent" and safety:
        body += '<span class="locked">tiene que tomarlo una persona</span>'
    return (
        f'<form class="editor" method="post" action="/tickets/{ticket_id}/in_progress">'
        f"{body}</form>"
    )


def _ticket_reason(reason: str) -> str:
    for prefix in REASON_PREFIXES:
        if reason.startswith(prefix):
            return reason[len(prefix):]
    return reason


def _ticket_id_cell(ticket: dict, tag: str) -> str:
    related = ticket.get("related_ticket_id")
    link = (
        f'<span class="brand">seguimiento de {escape(related)}</span>' if related else ""
    )
    return f'<td class="id">{escape(ticket["ticket_id"])}{tag}{link}</td>'


def _ticket_row(ticket: dict, names: dict[str, str], touched: str | None) -> str:
    ticket_id = ticket["ticket_id"]
    origin = ticket.get("origin") or "agent_request"
    origin_tone, origin_label = TICKET_ORIGIN_LABELS.get(origin, ("slate", origin.upper()))
    priority = ticket.get("priority") or "low"
    priority_tone = PRIORITY_TONES.get(priority, "slate")
    classes = " ".join(
        part
        for part in ("safety" if origin == "safety_risk" else "",
                     "touched" if ticket_id == touched else "")
        if part
    )
    tag = '<span class="tag">actualizado</span>' if ticket_id == touched else ""
    return (
        f'<tr class="{classes}">'
        f"{_ticket_id_cell(ticket, tag)}"
        f"<td>{_ticket_client_cell(ticket, names)}</td>"
        f'<td><span class="badge {origin_tone}">{escape(origin_label)}</span></td>'
        f'<td class="reason">{escape(_ticket_reason(ticket["reason"]))}</td>'
        f'<td><span class="badge {priority_tone}">{escape(priority.upper())}</span></td>'
        f"<td>{_ticket_state_cell(ticket)}</td>"
        f"<td>{_ticket_actions(ticket)}</td>"
        "</tr>"
    )


def _tickets_section(tickets: list[dict], names: dict[str, str], touched: str | None) -> str:
    if tickets:
        rows = "".join(_ticket_row(ticket, names, touched) for ticket in tickets)
    else:
        rows = (
            '<tr><td colspan="7" class="brand">Todavia no hay tickets. Radica un reclamo de '
            "garantia o pidele al agente hablar con una persona.</td></tr>"
        )
    return (
        "<section>"
        "<h2>Tickets de soporte</h2>"
        '<p class="hint">Aqui esta todo ticket que la tienda emite: todo reclamo de garantia, '
        "y ademas el cliente pidiendo hablar con una persona. Si el reclamo describe un riesgo "
        "de seguridad, la tienda lo marca sola. La columna <strong>Origen</strong> los "
        "distingue. Un ticket normal se cierra de una con su nota; uno de riesgo de seguridad "
        "tiene que tomarlo alguien antes, y la tienda rechaza cerrarlo sin eso. El numero que "
        'el agente le dio al cliente es el mismo que aparece aqui.</p>'
        '<div class="card"><table><thead><tr>'
        "<th>Ticket</th><th>Cliente</th><th>Origen</th><th>Motivo</th><th>Prioridad</th>"
        "<th>Estado</th><th>Mover</th>"
        "</tr></thead><tbody>" + rows + "</tbody></table></div></section>"
    )


def render_dashboard(
    orders: list[dict],
    warranties: list[dict],
    tickets: list[dict],
    names: dict[str, str],
    read_at: str,
    notice: str | None = None,
    problem: str | None = None,
    touched: str | None = None,
) -> str:
    banner = f'<div class="banner ok">{notice}</div>' if notice else ""
    if problem:
        banner += f'<div class="banner bad">{escape(problem)}</div>'
    body = (
        '<header class="masthead"><div>'
        "<h1>Consola de demostracion</h1>"
        '<p class="subtitle">Estado real de la tienda, leido del microservicio. Lo que cambies '
        "aqui es lo que el agente respondera.</p>"
        '</div><div class="right">'
        f'<a class="reload" href="/">Actualizar</a>'
        f'<div class="stamp">datos leidos a las {escape(read_at)}</div>'
        "</div></header>"
        + banner
        + _tickets_section(tickets, names, touched)
        + _orders_section(orders, names, touched)
        + _warranties_section(warranties, touched)
        + "<footer>Esta consola habla con el microservicio desde el servidor con la clave de "
        "operador: la cabecera <code>X-API-Key</code> nunca llega al navegador. Esa clave es "
        "distinta de la del agente, y es la que abre los listados completos; el agente no los "
        "puede leer ni aunque se le anadiera la herramienta.</footer>"
    )
    return _page("Consola de demostracion", body)


def render_unreachable(detail: str) -> str:
    body = (
        '<header class="masthead"><div><h1>Consola de demostracion</h1>'
        '<p class="subtitle">No se pudo leer el estado de la tienda.</p></div>'
        '<a class="reload" href="/">Reintentar</a></header>'
        f'<div class="banner bad">{escape(detail)}</div>'
    )
    return _page("Consola de demostracion", body)
