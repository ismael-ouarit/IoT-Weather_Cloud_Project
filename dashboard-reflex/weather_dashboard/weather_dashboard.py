"""SkySense — Weather Dashboard (Reflex prototype)"""
from __future__ import annotations

import reflex as rx

from .bq import load_overview

# ── Theme tokens ──────────────────────────────────────────────────────────────

BG_GRADIENT = "linear-gradient(180deg, #0E1525 0%, #131C30 100%)"
SIDEBAR_BG = "#0B1220"
CARD_BG = "linear-gradient(145deg, #1B2540 0%, #16213E 100%)"
HERO_BG = "linear-gradient(135deg, #2B1B5E 0%, #1B2540 60%, #16213E 100%)"
CARD_BORDER = "1px solid rgba(255, 255, 255, 0.05)"
SHADOW = "0 4px 12px rgba(0, 0, 0, 0.15)"
HOUR_BG = "rgba(40, 50, 80, 0.45)"

TEXT = "#FFFFFF"
MUTED = "#8899AA"
ACCENT = "#C9B6FF"


# ── State ─────────────────────────────────────────────────────────────────────

class State(rx.State):
    hours: int = 24

    indoor_temp: float = 0.0
    indoor_humidity: float = 0.0
    tvoc: float = 0.0
    eco2: float = 0.0

    outdoor_temp: float = 0.0
    outdoor_humidity: float = 0.0
    wind_speed: float = 0.0
    weather_condition: str = "—"
    weather_icon: str = "🌤️"

    high_today: float = 0.0
    low_today: float = 0.0

    recent: list[dict] = []
    alerts: list[dict] = []

    updated_at: str = ""
    day: str = ""
    date: str = ""

    page: str = "overview"

    @rx.event
    def load(self):
        data = load_overview(self.hours)
        for k, v in data.items():
            setattr(self, k, v)

    @rx.event
    def set_hours(self, hours: list[int | float]):
        self.hours = int(hours[0])
        return State.load

    @rx.event
    def set_page(self, page: str):
        self.page = page

    # ── computed ──────────────────────────────────────────────────────────
    @rx.var
    def indoor_temp_str(self) -> str:
        return f"{self.indoor_temp:.1f}" if self.indoor_temp else "—"

    @rx.var
    def outdoor_temp_str(self) -> str:
        return f"{self.outdoor_temp:.0f}" if self.outdoor_temp else "—"

    @rx.var
    def humidity_str(self) -> str:
        return f"{self.indoor_humidity:.0f}" if self.indoor_humidity else "—"

    @rx.var
    def tvoc_str(self) -> str:
        return f"{self.tvoc:.0f}" if self.tvoc else "—"

    @rx.var
    def eco2_str(self) -> str:
        return f"{self.eco2:.0f}" if self.eco2 else "—"

    @rx.var
    def wind_str(self) -> str:
        return f"{self.wind_speed:.1f}" if self.wind_speed else "—"

    @rx.var
    def range_str(self) -> str:
        if self.high_today and self.low_today:
            return f"High: {self.high_today:.0f}°  ·  Low: {self.low_today:.0f}°"
        return ""

    @rx.var
    def humidity_status(self) -> str:
        if not self.indoor_humidity:
            return ""
        if self.indoor_humidity >= 50: return "🟢 Good"
        if self.indoor_humidity >= 40: return "🟡 A bit low"
        return "🔴 Too low"

    @rx.var
    def tvoc_status(self) -> str:
        if not self.tvoc: return ""
        if self.tvoc < 65: return "🟢 Excellent"
        if self.tvoc < 220: return "🟢 Good"
        if self.tvoc < 660: return "🟡 Moderate"
        return "🔴 Poor"

    @rx.var
    def eco2_status(self) -> str:
        if not self.eco2: return ""
        if self.eco2 < 600: return "🟢 Normal"
        if self.eco2 < 800: return "🟢 Good"
        if self.eco2 < 1000: return "🟡 Moderate"
        return "🔴 High"

    @rx.var
    def wind_status(self) -> str:
        if not self.wind_speed: return ""
        if self.wind_speed < 5: return "🟢 Calm"
        if self.wind_speed < 10: return "🟡 Breezy"
        return "🔴 Windy"

    @rx.var
    def hours_label(self) -> str:
        return f"{self.hours}h" if self.hours < 48 else f"{self.hours // 24}d"


# ── Components ────────────────────────────────────────────────────────────────

def nav_item(label: str, icon: str, key: str) -> rx.Component:
    is_active = State.page == key
    return rx.box(
        rx.hstack(
            rx.icon(icon, size=18, color=rx.cond(is_active, TEXT, MUTED)),
            rx.text(label,
                    color=rx.cond(is_active, TEXT, MUTED),
                    weight="medium",
                    size="2"),
            spacing="3", align="center",
        ),
        on_click=State.set_page(key),
        padding="0.65rem 0.9rem",
        border_radius="10px",
        cursor="pointer",
        background=rx.cond(is_active, "rgba(140, 90, 255, 0.18)", "transparent"),
        _hover={"background": "rgba(255,255,255,0.04)"},
        width="100%",
    )


def sidebar() -> rx.Component:
    return rx.vstack(
        # Logo
        rx.vstack(
            rx.box(
                rx.icon("zap", size=28, color=ACCENT),
                background="rgba(140, 90, 255, 0.15)",
                padding="0.7rem", border_radius="14px",
            ),
            rx.heading("SkySense", size="4", color=TEXT, weight="bold"),
            rx.text("M5Stack · Lausanne", color=MUTED, size="1"),
            spacing="2", align="center", padding_y="1rem",
        ),
        rx.divider(color_scheme="gray"),
        rx.vstack(
            nav_item("Overview", "layout-dashboard", "overview"),
            nav_item("Trends", "trending-up", "trends"),
            nav_item("Air Quality", "wind", "air"),
            nav_item("Outdoor", "cloud-sun", "outdoor"),
            nav_item("Statistics", "bar-chart-3", "stats"),
            spacing="1", width="100%", padding_top="0.6rem",
        ),
        rx.spacer(),
        rx.text(f"Updated", color=MUTED, size="1"),
        rx.text(State.updated_at, color=TEXT, size="1", weight="medium"),
        height="100vh",
        width="240px",
        padding="1.5rem 1rem",
        background=SIDEBAR_BG,
        border_right="1px solid rgba(255,255,255,0.04)",
        spacing="2",
    )


def hero_card() -> rx.Component:
    return rx.box(
        rx.vstack(
            # Location pill
            rx.box(
                rx.hstack(
                    rx.icon("map-pin", size=14, color=ACCENT),
                    rx.text("Lausanne, CH", color=ACCENT, size="2", weight="bold"),
                    spacing="1", align="center",
                ),
                background="rgba(140, 90, 255, 0.18)",
                padding="0.4rem 0.9rem", border_radius="999px",
                display="inline-block",
            ),
            rx.box(height="0.5rem"),
            rx.heading(State.day, size="8", color=TEXT, weight="bold"),
            rx.text(State.date, color=MUTED, size="2"),
            rx.box(height="0.8rem"),
            rx.hstack(
                rx.vstack(
                    rx.hstack(
                        rx.heading(State.outdoor_temp_str, size="9", color=TEXT, weight="bold",
                                   style={"line_height": "1"}),
                        rx.text("°C", color=MUTED, size="5", margin_top="0.5rem"),
                        spacing="1", align="end",
                    ),
                    rx.text(State.range_str, color=MUTED, size="2"),
                    align="start", spacing="2",
                ),
                rx.spacer(),
                rx.vstack(
                    rx.text(State.weather_icon, font_size="5rem",
                            style={"line_height": "1"}),
                    rx.heading(State.weather_condition, size="5", color=TEXT, weight="bold"),
                    rx.text(f"Feels like {State.outdoor_temp_str}°", color=MUTED, size="2"),
                    align="end", spacing="1",
                ),
                width="100%", align="end",
            ),
            spacing="0", align="start", width="100%",
        ),
        background=HERO_BG, border_radius="22px",
        padding="1.8rem 2rem", border=CARD_BORDER, box_shadow=SHADOW,
        width="100%",
    )


def highlight_card(icon: str, label: str, value: rx.Var, unit: str, status: rx.Var) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon(icon, size=16, color=MUTED),
                rx.text(label, color=MUTED, size="2", weight="medium"),
                spacing="2", align="center",
            ),
            rx.hstack(
                rx.heading(value, size="7", color=TEXT, weight="bold"),
                rx.text(unit, color=MUTED, size="2", margin_top="0.4rem"),
                spacing="1", align="end",
            ),
            rx.text(status, color=MUTED, size="1"),
            spacing="2", align="start",
        ),
        background=CARD_BG, border_radius="16px", padding="1.1rem 1.2rem",
        border=CARD_BORDER, box_shadow=SHADOW, width="100%",
    )


def highlights() -> rx.Component:
    return rx.vstack(
        rx.heading("Today's Highlights", size="4", color=TEXT, weight="bold"),
        rx.grid(
            highlight_card("droplets", "Humidity", State.humidity_str, "%", State.humidity_status),
            highlight_card("leaf", "Air Quality (TVOC)", State.tvoc_str, "ppb", State.tvoc_status),
            highlight_card("wind", "Wind Status", State.wind_str, "m/s", State.wind_status),
            highlight_card("cloud", "eCO₂", State.eco2_str, "ppm", State.eco2_status),
            columns="2", spacing="3", width="100%",
        ),
        spacing="3", width="100%",
    )


def hour_card(item: rx.Var) -> rx.Component:
    return rx.vstack(
        rx.text(item["time"], color=MUTED, size="1", weight="bold"),
        rx.text("🌡️", font_size="1.6rem"),
        rx.text(f"{item['temp']}°", color=TEXT, size="3", weight="bold"),
        background=HOUR_BG, border_radius="14px",
        padding="0.9rem 0.5rem", border="1px solid rgba(255,255,255,0.04)",
        spacing="1", align="center", flex="1",
    )


def recent_readings() -> rx.Component:
    return rx.vstack(
        rx.heading("Recent Readings", size="4", color=TEXT, weight="bold"),
        rx.box(
            rx.cond(
                State.recent.length() > 0,
                rx.hstack(
                    rx.foreach(State.recent, hour_card),
                    spacing="2", width="100%",
                ),
                rx.text("No recent sensor data.", color=MUTED, size="2"),
            ),
            background=CARD_BG, border_radius="18px",
            padding="1.2rem", border=CARD_BORDER, box_shadow=SHADOW, width="100%",
        ),
        spacing="3", width="100%",
    )


def alert_row(alert: rx.Var) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.text(alert["icon"], font_size="1.3rem"),
            rx.text(alert["label"], color=TEXT, size="3", weight="bold"),
            spacing="2", align="center",
        ),
        rx.text(alert["value"], color=MUTED, size="2", padding_left="2rem"),
        spacing="1", align="start",
        padding_y="0.5rem",
        border_bottom="1px solid rgba(255,255,255,0.05)", width="100%",
    )


def alerts_panel() -> rx.Component:
    return rx.vstack(
        rx.heading("Active Alerts", size="4", color=TEXT, weight="bold"),
        rx.box(
            rx.cond(
                State.alerts.length() > 0,
                rx.vstack(
                    rx.foreach(State.alerts, alert_row),
                    spacing="0", width="100%",
                ),
                rx.vstack(
                    rx.text("✅", font_size="2.5rem"),
                    rx.text("All systems nominal", color=MUTED, size="2"),
                    spacing="2", align="center", padding_y="1.5rem", width="100%",
                ),
            ),
            background=CARD_BG, border_radius="18px",
            padding="1.2rem", border=CARD_BORDER, box_shadow=SHADOW,
            width="100%", min_height="220px",
        ),
        spacing="3", width="100%",
    )


def topbar() -> rx.Component:
    return rx.hstack(
        rx.vstack(
            rx.heading("Overview", size="6", color=TEXT, weight="bold"),
            rx.text("Real-time indoor & outdoor conditions", color=MUTED, size="2"),
            align="start", spacing="1",
        ),
        rx.spacer(),
        rx.vstack(
            rx.text(f"Time range: {State.hours_label}", color=MUTED, size="1"),
            rx.slider(
                default_value=24, min=6, max=168, step=6,
                on_value_commit=State.set_hours,
                width="200px",
                color_scheme="violet",
            ),
            spacing="1", align="end",
        ),
        rx.button(
            rx.icon("rotate-ccw", size=16),
            "Refresh",
            on_click=State.load,
            variant="soft",
            color_scheme="violet",
        ),
        width="100%", align="center", spacing="4",
    )


def overview_page() -> rx.Component:
    return rx.vstack(
        topbar(),
        rx.box(height="0.5rem"),
        rx.grid(
            hero_card(),
            highlights(),
            columns="2", spacing="4", width="100%",
        ),
        rx.box(height="0.5rem"),
        rx.grid(
            recent_readings(),
            alerts_panel(),
            columns="7fr 4fr", spacing="4", width="100%",
        ),
        spacing="4", width="100%",
    )


def coming_soon(name: str) -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.text("🚧", font_size="4rem"),
            rx.heading(f"{name}", size="6", color=TEXT),
            rx.text("This page will be ported next.", color=MUTED, size="2"),
            spacing="3", align="center",
        ),
        height="60vh", width="100%",
    )


def index() -> rx.Component:
    return rx.hstack(
        sidebar(),
        rx.box(
            rx.match(
                State.page,
                ("overview", overview_page()),
                ("trends", coming_soon("Trends")),
                ("air", coming_soon("Air Quality")),
                ("outdoor", coming_soon("Outdoor")),
                ("stats", coming_soon("Statistics")),
                overview_page(),
            ),
            padding="2rem 2.5rem", flex="1", min_height="100vh",
            overflow="auto",
        ),
        spacing="0", align="start",
        background=BG_GRADIENT, min_height="100vh", width="100%",
    )


app = rx.App(
    theme=rx.theme(appearance="dark", accent_color="violet", radius="large", scaling="100%"),
    style={"font_family": "Inter, ui-sans-serif, system-ui, sans-serif"},
)
app.add_page(index, on_load=State.load, title="SkySense · Weather Station")
