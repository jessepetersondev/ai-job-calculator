"""
PDF report generator for the AI Job Vulnerability Calculator.
Generates a 4-5 page personalized report worth the $9 price point.

Layout:
  Page 1 — Cover: name + score + headline framing
  Page 2 — Your Vulnerability Profile (numbers + 5-year trajectory)
  Page 3 — What AI Is Replacing In Your Role + Adjacent Safer Roles
  Page 4 — Skills to Learn + 90-day Pivot Plan
  Page 5 — Methodology & Sources

Uses ReportLab (pure Python, no external binaries).
"""

import io
from datetime import datetime, timezone
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
    KeepTogether, Flowable, ListFlowable, ListItem
)
from reportlab.pdfgen import canvas


# ─── Brand colors ───────────────────────────────────────────────
INK         = colors.HexColor("#0d0c0a")
INK_2       = colors.HexColor("#15140f")
BONE        = colors.HexColor("#f4ecd8")
BONE_2      = colors.HexColor("#d9d1bf")
BONE_3      = colors.HexColor("#8a8576")
SIGNAL      = colors.HexColor("#ff4d2e")
GOLD        = colors.HexColor("#d4a73e")
HEAT_LOW    = colors.HexColor("#4a9b8e")
HEAT_MED    = colors.HexColor("#e6a23d")
HEAT_HIGH   = colors.HexColor("#d65a31")
HEAT_EXTREME= colors.HexColor("#b3361f")
RULE_LIGHT  = colors.HexColor("#cfc7b3")


def heat_color(pct: float):
    if pct >= 40: return HEAT_EXTREME
    if pct >= 25: return HEAT_HIGH
    if pct >= 12: return HEAT_MED
    if pct >=  5: return HEAT_LOW
    return colors.HexColor("#2b6e6f")


# ─── Custom flowables ───────────────────────────────────────────
class HRule(Flowable):
    def __init__(self, width, thickness=0.5, color=RULE_LIGHT):
        Flowable.__init__(self)
        self.width = width
        self.thickness = thickness
        self.color = color
    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, 0, self.width, 0)


class HeatBar(Flowable):
    """Horizontal bar showing the user's vulnerability vs. national average."""
    def __init__(self, pct, width=5*inch, height=0.32*inch, max_pct=60):
        Flowable.__init__(self)
        self.pct = pct
        self.width = width
        self.height = height
        self.max_pct = max_pct

    def draw(self):
        c = self.canv
        # Track
        c.setFillColor(colors.HexColor("#e8e0cd"))
        c.rect(0, 0, self.width, self.height, stroke=0, fill=1)
        # Fill
        fill_w = (min(self.pct, self.max_pct) / self.max_pct) * self.width
        c.setFillColor(heat_color(self.pct))
        c.rect(0, 0, fill_w, self.height, stroke=0, fill=1)
        # Tick marks every 20%
        c.setStrokeColor(colors.white)
        c.setLineWidth(0.5)
        for t in range(1, int(self.max_pct / 10)):
            x = (t * 10 / self.max_pct) * self.width
            c.line(x, 0, x, self.height)
        # Border
        c.setStrokeColor(colors.HexColor("#8a8576"))
        c.setLineWidth(0.5)
        c.rect(0, 0, self.width, self.height, stroke=1, fill=0)


class TrajectoryChart(Flowable):
    """5-year trajectory line chart."""
    def __init__(self, trajectory, width=6*inch, height=2.2*inch):
        Flowable.__init__(self)
        self.trajectory = trajectory
        self.width = width
        self.height = height

    def draw(self):
        c = self.canv
        margin_l, margin_r, margin_t, margin_b = 40, 20, 18, 32
        chart_w = self.width - margin_l - margin_r
        chart_h = self.height - margin_t - margin_b

        max_y = max(p["pct"] for p in self.trajectory)
        max_y = max(max_y, 20)  # min ceiling for readability
        max_y = math_ceil(max_y, step=10)

        # Y-axis grid + labels
        c.setFont("Helvetica", 7)
        c.setFillColor(BONE_3)
        for i in range(0, 5):
            y_val = max_y * i / 4
            y_px = margin_b + chart_h * i / 4
            c.setStrokeColor(colors.HexColor("#e8e0cd"))
            c.setLineWidth(0.3)
            c.line(margin_l, y_px, self.width - margin_r, y_px)
            c.drawRightString(margin_l - 4, y_px - 2, f"{int(y_val)}%")

        # X-axis: years
        n = len(self.trajectory)
        for i, p in enumerate(self.trajectory):
            x_px = margin_l + chart_w * i / (n - 1)
            c.setFillColor(BONE_3)
            c.drawCentredString(x_px, margin_b - 14, str(p["year"]))

        # Line
        pts = []
        for i, p in enumerate(self.trajectory):
            x_px = margin_l + chart_w * i / (n - 1)
            y_px = margin_b + chart_h * (p["pct"] / max_y)
            pts.append((x_px, y_px))

        # Filled area under line
        c.setFillColor(colors.HexColor("#ff4d2e"))
        c.setFillAlpha(0.10)
        path = c.beginPath()
        path.moveTo(pts[0][0], margin_b)
        for x, y in pts:
            path.lineTo(x, y)
        path.lineTo(pts[-1][0], margin_b)
        path.close()
        c.drawPath(path, stroke=0, fill=1)
        c.setFillAlpha(1.0)

        # Line
        c.setStrokeColor(SIGNAL)
        c.setLineWidth(1.8)
        for i in range(len(pts) - 1):
            c.line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])

        # Dots + value labels
        for i, (x, y) in enumerate(pts):
            c.setFillColor(SIGNAL)
            c.circle(x, y, 2.5, stroke=0, fill=1)
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 7)
            c.drawCentredString(x, y + 7, f"{self.trajectory[i]['pct']}%")


def math_ceil(n, step=10):
    return int(((n + step - 1) // step) * step)


# ─── Styles ─────────────────────────────────────────────────────
def _styles():
    s = getSampleStyleSheet()

    s.add(ParagraphStyle("CoverTitle",
        fontName="Helvetica-Bold", fontSize=42, leading=44,
        textColor=INK, spaceAfter=6, alignment=TA_LEFT))

    s.add(ParagraphStyle("CoverSub",
        fontName="Helvetica", fontSize=14, leading=18,
        textColor=BONE_3, spaceAfter=20, alignment=TA_LEFT))

    s.add(ParagraphStyle("BigScore",
        fontName="Helvetica-Bold", fontSize=96, leading=96,
        textColor=SIGNAL, spaceAfter=2, alignment=TA_LEFT))

    s.add(ParagraphStyle("ScoreLabel",
        fontName="Helvetica", fontSize=11, leading=14,
        textColor=BONE_3, spaceAfter=20, alignment=TA_LEFT))

    s.add(ParagraphStyle("H1",
        fontName="Helvetica-Bold", fontSize=22, leading=26,
        textColor=INK, spaceBefore=18, spaceAfter=8))

    s.add(ParagraphStyle("H2",
        fontName="Helvetica-Bold", fontSize=14, leading=18,
        textColor=INK, spaceBefore=14, spaceAfter=6))

    s.add(ParagraphStyle("Eyebrow",
        fontName="Helvetica-Bold", fontSize=8, leading=10,
        textColor=SIGNAL, spaceAfter=4))

    s.add(ParagraphStyle("Body",
        fontName="Helvetica", fontSize=10.5, leading=15,
        textColor=INK, spaceAfter=8))

    s.add(ParagraphStyle("Lede",
        fontName="Helvetica-Oblique", fontSize=12, leading=17,
        textColor=colors.HexColor("#3a3830"), spaceAfter=12))

    s.add(ParagraphStyle("Small",
        fontName="Helvetica", fontSize=8.5, leading=12,
        textColor=BONE_3, spaceAfter=4))

    s.add(ParagraphStyle("Pull",
        fontName="Helvetica-Oblique", fontSize=14, leading=19,
        textColor=INK_2, spaceBefore=10, spaceAfter=14,
        leftIndent=14, borderPadding=0))

    s.add(ParagraphStyle("Item",
        fontName="Helvetica", fontSize=10.5, leading=15,
        textColor=INK, leftIndent=14, spaceAfter=4,
        bulletIndent=0))

    return s


# ─── Header/Footer on each page ─────────────────────────────────
def _on_page(canvas_obj, doc):
    """Header + footer drawn on every page."""
    page_num = doc.page

    # Footer
    canvas_obj.saveState()
    canvas_obj.setFont("Helvetica", 7.5)
    canvas_obj.setFillColor(BONE_3)
    canvas_obj.drawString(0.6*inch, 0.45*inch, "THE GREAT REPLACEMENT — Personalized Vulnerability Report")
    canvas_obj.drawRightString(letter[0] - 0.6*inch, 0.45*inch, f"Page {page_num}")

    # Top rule on non-cover pages
    if page_num > 1:
        canvas_obj.setStrokeColor(RULE_LIGHT)
        canvas_obj.setLineWidth(0.5)
        canvas_obj.line(0.6*inch, letter[1] - 0.5*inch,
                        letter[0] - 0.6*inch, letter[1] - 0.5*inch)
        canvas_obj.setFont("Helvetica-Bold", 7.5)
        canvas_obj.setFillColor(SIGNAL)
        canvas_obj.drawString(0.6*inch, letter[1] - 0.4*inch, "/ ATLAS REPORT")

    canvas_obj.restoreState()


# ─── Main build function ────────────────────────────────────────
def build_pdf(occ, state_code, state_name, state_pct, result,
              skill_resources, national_avg) -> bytes:
    """Build the personalized PDF report and return bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.6*inch, rightMargin=0.6*inch,
        topMargin=0.7*inch, bottomMargin=0.7*inch,
        title=f"AI Vulnerability Report — {occ['title']}",
        author="The Great Replacement Atlas"
    )
    st = _styles()
    story = []

    pct = result["vulnerability_pct"]
    rank = result["rank"]
    total = result["total"]

    # ============================================================
    # PAGE 1 — COVER
    # ============================================================
    story.append(Spacer(1, 0.4*inch))
    story.append(Paragraph("PERSONALIZED VULNERABILITY REPORT", st["Eyebrow"]))
    story.append(Paragraph("The Great<br/>Replacement.", st["CoverTitle"]))
    story.append(HRule(letter[0] - 1.2*inch))
    story.append(Spacer(1, 0.3*inch))

    story.append(Paragraph("YOUR PROJECTED 5-YEAR VULNERABILITY", st["Eyebrow"]))
    story.append(Paragraph(f"{pct}<font size='32' color='#8a8576'>%</font>", st["BigScore"]))
    story.append(Paragraph(
        f"<b>{occ['title']}</b> &nbsp; · &nbsp; {state_name} &nbsp; · &nbsp; ranked #{rank} of {total} occupations analyzed",
        st["ScoreLabel"]))

    story.append(HeatBar(pct, width=letter[0] - 1.2*inch))
    story.append(Spacer(1, 0.08*inch))
    story.append(Paragraph(
        f"<font color='#8a8576'>0% &nbsp;&nbsp; safe</font>"
        f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font color='#b3361f'>60%+ &nbsp;&nbsp; extreme</font>",
        st["Small"]))
    story.append(Spacer(1, 0.3*inch))

    story.append(Paragraph(
        f"<i>{result['severity_label']}</i>",
        st["Lede"]))

    story.append(Spacer(1, 0.2*inch))
    story.append(HRule(letter[0] - 1.2*inch, color=BONE_3))
    story.append(Spacer(1, 0.1*inch))

    # Key facts table
    facts_data = [
        ["YOUR ROLE",              occ["title"]],
        ["STATE",                  f"{state_name} ({state_code})"],
        ["INDUSTRY CATEGORY",      occ["category"]],
        ["NATIONAL AVERAGE",       f"{national_avg}% across all occupations"],
        ["YOUR STATE'S AVERAGE",   f"{state_pct}% of all jobs"],
        ["REPORT DATE",            datetime.now(timezone.utc).strftime("%B %d, %Y")],
    ]
    facts_tbl = Table(facts_data, colWidths=[1.7*inch, 4.5*inch], hAlign="LEFT")
    facts_tbl.setStyle(TableStyle([
        ("FONT",       (0,0), (0,-1), "Helvetica-Bold", 7.5),
        ("FONT",       (1,0), (1,-1), "Helvetica",      9.5),
        ("TEXTCOLOR",  (0,0), (0,-1), BONE_3),
        ("TEXTCOLOR",  (1,0), (1,-1), INK),
        ("LINEBELOW",  (0,0), (-1,-1), 0.3, RULE_LIGHT),
        ("LEFTPADDING",(0,0),(-1,-1), 0),
        ("RIGHTPADDING",(0,0),(-1,-1),0),
        ("TOPPADDING", (0,0),(-1,-1),5),
        ("BOTTOMPADDING",(0,0),(-1,-1),5),
        ("VALIGN",     (0,0),(-1,-1), "TOP"),
    ]))
    story.append(facts_tbl)

    story.append(PageBreak())

    # ============================================================
    # PAGE 2 — VULNERABILITY PROFILE + TRAJECTORY
    # ============================================================
    story.append(Paragraph("SECTION 01", st["Eyebrow"]))
    story.append(Paragraph("Your vulnerability profile.", st["H1"]))
    story.append(HRule(letter[0] - 1.2*inch))
    story.append(Spacer(1, 0.15*inch))

    # Three-stat row
    stats_data = [[
        Paragraph(f"<b><font size='28' color='#ff4d2e'>{pct}%</font></b><br/>"
                  f"<font size='7' color='#8a8576'>YOUR 2–5 YEAR<br/>VULNERABILITY</font>", st["Body"]),
        Paragraph(f"<b><font size='28'>#{rank}</font></b><br/>"
                  f"<font size='7' color='#8a8576'>RANK ACROSS<br/>{total} OCCUPATIONS</font>", st["Body"]),
        Paragraph(f"<b><font size='28'>{result['exposure']}<font size='14'>/100</font></font></b><br/>"
                  f"<font size='7' color='#8a8576'>AI EXPOSURE<br/>SCORE</font>", st["Body"]),
    ]]
    stats_tbl = Table(stats_data, colWidths=[2.07*inch]*3, hAlign="LEFT")
    stats_tbl.setStyle(TableStyle([
        ("VALIGN", (0,0),(-1,-1), "TOP"),
        ("LINEAFTER", (0,0),(0,0), 0.4, RULE_LIGHT),
        ("LINEAFTER", (1,0),(1,0), 0.4, RULE_LIGHT),
        ("LEFTPADDING", (0,0),(-1,-1), 0),
        ("RIGHTPADDING",(0,0),(-1,-1), 14),
        ("LEFTPADDING", (1,0),(2,0), 14),
    ]))
    story.append(stats_tbl)
    story.append(Spacer(1, 0.25*inch))

    # Comparison
    story.append(Paragraph("WHERE YOU STAND", st["Eyebrow"]))
    diff = pct - national_avg
    if diff > 0:
        comparison = (f"Your role is <b>{diff:.1f} percentage points above</b> the national "
                      f"average for AI vulnerability across all US occupations.")
    elif diff < 0:
        comparison = (f"Your role is <b>{abs(diff):.1f} percentage points below</b> the national "
                      f"average — most US workers face more AI exposure than you do.")
    else:
        comparison = "Your role sits roughly at the national average for AI vulnerability."
    story.append(Paragraph(comparison, st["Body"]))

    # Trajectory chart
    story.append(Spacer(1, 0.15*inch))
    story.append(Paragraph("FIVE-YEAR DISPLACEMENT TRAJECTORY", st["Eyebrow"]))
    story.append(Paragraph(
        f"Modeled as a logistic adoption curve. Half-saturation reached around <b>{result['half_saturation_yr']}</b>; "
        f"projected ceiling near <b>{result['ceiling']}%</b> by 2045.",
        st["Body"]))
    story.append(TrajectoryChart(result["trajectory"], width=letter[0] - 1.2*inch))
    story.append(Spacer(1, 0.1*inch))
    story.append(Paragraph(
        "This is a scenario projection based on logistic AI-adoption curves anchored to "
        "McKinsey's 2030–2060 half-saturation band. Real outcomes depend on regulation, "
        "firm decisions, and the pace of capability gains.",
        st["Small"]))

    story.append(PageBreak())

    # ============================================================
    # PAGE 3 — WHAT AI IS REPLACING + ADJACENT SAFER ROLES
    # ============================================================
    story.append(Paragraph("SECTION 02", st["Eyebrow"]))
    story.append(Paragraph("What AI is replacing in your role.", st["H1"]))
    story.append(HRule(letter[0] - 1.2*inch))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph(
        f"Based on real-world usage data from the Anthropic Economic Index, Tomlinson et al. (2025) "
        f"Microsoft Copilot study, and BLS occupational task profiles, these tasks in <b>{occ['title']}</b> "
        f"are the highest-risk for near-term AI substitution:",
        st["Body"]))

    bullets = [Paragraph(f"<b>·</b> &nbsp; {t}", st["Item"]) for t in result["at_risk_tasks"]]
    for b in bullets:
        story.append(b)

    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph(
        "Note: 'task replacement' does not equal 'job replacement.' AI usually substitutes for "
        "<i>parts</i> of a job before whole roles disappear. The pattern we see across the data: as more "
        "of your tasks become automatable, demand for workers in your role declines first through "
        "reduced hiring, then through attrition, and finally through layoffs — usually in that order.",
        st["Body"]))

    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph("SECTION 03", st["Eyebrow"]))
    story.append(Paragraph("Adjacent safer roles.", st["H1"]))
    story.append(HRule(letter[0] - 1.2*inch))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph(
        "These adjacent roles share significant skill overlap with your current role but face "
        "<b>materially lower</b> AI vulnerability. They are ranked by transferability of the "
        "skills you likely already have:",
        st["Body"]))
    story.append(Spacer(1, 0.1*inch))

    adj = result["adjacent_safer"]
    rows = []
    for i, role in enumerate(adj, 1):
        rows.append([
            Paragraph(f"<font color='#ff4d2e'><b>{i:02d}</b></font>", st["Body"]),
            Paragraph(f"<b>{role}</b>", st["Body"]),
            Paragraph(f"<font color='#8a8576' size='8'>HIGH SKILL OVERLAP</font>", st["Small"])
        ])
    adj_tbl = Table(rows, colWidths=[0.4*inch, 4.3*inch, 1.5*inch], hAlign="LEFT")
    adj_tbl.setStyle(TableStyle([
        ("VALIGN", (0,0),(-1,-1), "MIDDLE"),
        ("LINEBELOW", (0,0),(-1,-1), 0.3, RULE_LIGHT),
        ("TOPPADDING", (0,0),(-1,-1), 10),
        ("BOTTOMPADDING", (0,0),(-1,-1), 10),
    ]))
    story.append(adj_tbl)

    story.append(PageBreak())

    # ============================================================
    # PAGE 4 — SKILLS + 90-DAY PIVOT PLAN
    # ============================================================
    story.append(Paragraph("SECTION 04", st["Eyebrow"]))
    story.append(Paragraph("Skills to build &mdash; with resources.", st["H1"]))
    story.append(HRule(letter[0] - 1.2*inch))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph(
        "These are the skills with the highest demand growth in your category and the lowest "
        "AI exposure. The course recommendations are starting points, not endorsements — pick "
        "ones that match your learning style and budget:",
        st["Body"]))
    story.append(Spacer(1, 0.1*inch))

    default_res = skill_resources.get("default", {})
    skill_rows = []
    for skill in result["skills_to_learn"]:
        res = skill_resources.get(skill, default_res)
        skill_rows.append([
            Paragraph(f"<b>{skill}</b><br/>"
                      f"<font size='8.5' color='#8a8576'>Resource: {res.get('course', '—')}</font>",
                      st["Body"]),
            Paragraph(f"<font size='7.5' color='#8a8576'>LINK</font><br/>"
                      f"<font size='7.5'>{res.get('url', '—')}</font>",
                      st["Small"])
        ])
    skill_tbl = Table(skill_rows, colWidths=[3.8*inch, 2.4*inch], hAlign="LEFT")
    skill_tbl.setStyle(TableStyle([
        ("VALIGN", (0,0),(-1,-1), "TOP"),
        ("LINEBELOW", (0,0),(-1,-1), 0.3, RULE_LIGHT),
        ("TOPPADDING", (0,0),(-1,-1), 10),
        ("BOTTOMPADDING", (0,0),(-1,-1), 10),
    ]))
    story.append(skill_tbl)

    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph("SECTION 05", st["Eyebrow"]))
    story.append(Paragraph("Your 90-day pivot plan.", st["H1"]))
    story.append(HRule(letter[0] - 1.2*inch))
    story.append(Spacer(1, 0.1*inch))

    plan = [
        ("Days 1–14",  "Audit your current role honestly. Which of your tasks (listed on the previous page) is AI already doing for your coworkers? Talk to 3 people in your org who use AI daily."),
        ("Days 15–30", "Pick ONE adjacent role from Section 03. Study its job descriptions on LinkedIn — list the skills it requires that you don't yet have."),
        ("Days 31–60", "Start ONE of the skill investments from Section 04. Stack-rank by what shows up most in those job descriptions, not by what's intellectually interesting."),
        ("Days 61–80", "Build a portfolio artifact in your new direction — a project, certification, or visible output that demonstrates the new skill."),
        ("Days 81–90", "Apply to 5–10 roles. Update LinkedIn and resume to reflect the pivot. Don't quit your current job yet — let the market tell you if you're ready."),
    ]
    for label, txt in plan:
        story.append(Paragraph(f"<b>{label}</b>", st["H2"]))
        story.append(Paragraph(txt, st["Body"]))

    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph(
        "<i>The hardest part of any career pivot is starting. The data in this report exists to "
        "give you a structured starting point — not to predict the future. Adjust as you learn.</i>",
        st["Pull"]))

    story.append(PageBreak())

    # ============================================================
    # PAGE 5 — METHODOLOGY
    # ============================================================
    story.append(Paragraph("APPENDIX", st["Eyebrow"]))
    story.append(Paragraph("Methodology &amp; sources.", st["H1"]))
    story.append(HRule(letter[0] - 1.2*inch))
    story.append(Spacer(1, 0.1*inch))

    story.append(Paragraph(
        "This report uses occupation-level vulnerability scores from the Tufts University Digital "
        "Planet <i>American AI Jobs Risk Index</i> (March 2026), which combines theoretical exposure "
        "measures (Eloundou et al., 2023) with real-world usage data from the Anthropic Economic "
        "Index (2025) and the Microsoft Copilot study (Tomlinson et al., 2025).",
        st["Body"]))
    story.append(Paragraph(
        "State-level percentages reflect each state's industry composition. Your personalized "
        "score modifies the base occupational vulnerability by your state's mix, with the modifier "
        "capped at ±20% of the base.",
        st["Body"]))
    story.append(Paragraph(
        "Five-year trajectory curves are logistic adoption models calibrated to McKinsey Global "
        "Institute's 2030–2060 half-saturation band. No industry is forecast to reach 100% "
        "saturation; physical work, regulatory floors, licensure, and trust-dependent decisions "
        "all leave a permanent human residue.",
        st["Body"]))

    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph("PRIMARY SOURCES", st["Eyebrow"]))
    sources = [
        ("Tufts Digital Planet (Mar 2026)", "Will Wired Belts Become the New Rust Belts? AI and the Emerging Geography of American Job Risk"),
        ("Anthropic (2025)",                "Anthropic Economic Index — Labor Market Impacts of AI"),
        ("Tomlinson et al. (2025)",         "Microsoft Copilot Real-World Usage Data"),
        ("Goldman Sachs (2025–26)",         "How Will AI Affect the Global Workforce?"),
        ("McKinsey Global Institute",       "The Economic Potential of Generative AI"),
        ("Brookings Institution (2026)",    "Measuring US Workers' Capacity to Adapt to AI-Driven Job Displacement"),
        ("World Economic Forum",            "Future of Jobs Report 2025"),
        ("Stanford Digital Economy Lab",    "Canaries in the Coal Mine (Brynjolfsson et al. 2025)"),
    ]
    src_rows = [[Paragraph(f"<b>{p}</b>", st["Small"]), Paragraph(t, st["Small"])] for p, t in sources]
    src_tbl = Table(src_rows, colWidths=[1.8*inch, 4.4*inch], hAlign="LEFT")
    src_tbl.setStyle(TableStyle([
        ("VALIGN", (0,0),(-1,-1), "TOP"),
        ("LINEBELOW", (0,0),(-1,-1), 0.3, RULE_LIGHT),
        ("TOPPADDING", (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
    ]))
    story.append(src_tbl)

    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph("IMPORTANT CAVEAT", st["Eyebrow"]))
    story.append(Paragraph(
        "These projections are <b>scenarios, not forecasts</b>. AI capabilities, adoption speed, "
        "regulation, and firm behavior are evolving faster than any single study can capture. "
        "Your personal trajectory will be shaped by far more than this score: by your specific "
        "employer, location, network, willingness to retrain, and luck. Use this report as a "
        "starting framework, not a verdict.",
        st["Small"]))

    # Build
    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return buf.getvalue()
