"""Formatea los resultados del análisis para mostrarlos en Telegram.

Los mensajes siguen un formato consistente y escaneable:
- Uso de emojis ML (🏟️, 📊, 🎯, etc.) para secciones.
- Tablas en formato código para alineación.
- Tono profesional y basado en datos.
"""
from typing import Dict, List, Optional


def format_prediction_message(prediction: dict, home_name: str,
                              away_name: str, date: str = "") -> str:
    """Genera el mensaje completo de recomendación para un partido.

    Args:
        prediction: dict con 'probabilities', 'expected_goals',
            'recommendations', 'h2h_available'.
        home_name: nombre del equipo local.
        away_name: nombre del equipo visitante.
        date: fecha del partido (opcional).
    """
    lines = []

    header = f"📊 ANÁLISIS PREDICTIVO DE APUESTAS"
    if date:
        header += f"\n📅 Fecha: {date}"
    lines.append(header)

    # Encabezado del partido
    lines.append("")
    lines.append(f"🏟️ {home_name} vs {away_name}")

    # Probabilidades
    probs = prediction.get("probabilities", {})
    eg = prediction.get("expected_goals", {})
    lines.append("")
    lines.append("📈 Probabilidades:")
    lines.append(
        f"   • Local {home_name}: {probs.get('1', 0)*100:.0f}%"
    )
    lines.append(f"   • Empate: {probs.get('draw', 0)*100:.0f}%")
    lines.append(
        f"   • Visitante {away_name}: {probs.get('2', 0)*100:.0f}%"
    )
    lines.append(
        f"   • Over 2.5: {probs.get('over_2.5', 0)*100:.0f}% | "
        f"BTTS Sí: {probs.get('btts_yes', 0)*100:.0f}%"
    )

    lines.append("")
    lines.append(
        f"⚽ Goles esperados (Poisson): "
        f"{eg.get('home', 0):.2f} - {eg.get('away', 0):.2f} "
        f"(total {eg.get('total', 0):.2f})"
    )

    # Recomendaciones
    recs = prediction.get("recommendations", [])
    if recs:
        lines.append("")
        lines.append("🎯 RECOMENDACIONES (ordenadas por confianza):")
        for i, rec in enumerate(recs, start=1):
            status = "✅" if rec.get("recommended") else "⬜"
            lines.append(
                f"   {status} {i}. {rec.get('pick_text', '')} "
                f"({rec.get('confidence', '')}) - "
                f"{rec.get('probability', 0)*100:.0f}%"
            )
            if rec.get("odds"):
                lines.append(
                    f"      Cuota: {rec['odds']} | Edge: {rec.get('edge', 0):+.2%}"
                )

    # Nota sobre H2H
    if not prediction.get("h2h_available"):
        lines.append("")
        lines.append("⚠️ Nota: No hay suficientes enfrentamientos directos.")

    lines.append("")
    lines.append("⚠️ El análisis es estadístico y NO garantiza resultados.")

    return "\n".join(lines)


def format_comparison_table(stats_data: Dict, home_name: str,
                            away_name: str) -> str:
    """Genera la tabla comparativa de estadísticas entre ambos equipos.

    Args:
        stats_data: dict con 'home' y 'away', cada uno con métricas.
    """
    home = stats_data.get("home", {})
    away = stats_data.get("away", {})

    rows = [
        ("Posición en liga", home.get("position", "-"),
         away.get("position", "-")),
        ("Goles/partido", home.get("goals_per_game", "-"),
         away.get("goals_per_game", "-")),
        ("Goles recibidos/partido", home.get("conceded_per_game", "-"),
         away.get("conceded_per_game", "-")),
        ("Remates a puerta/partido", home.get("shots_on_target_per_game", "-"),
         away.get("shots_on_target_per_game", "-")),
        ("Tiros esquina/partido", home.get("corners_per_game", "-"),
         away.get("corners_per_game", "-")),
        ("Posesión promedio", f"{home.get('possession_avg', 0)}%",
         f"{away.get('possession_avg', 0)}%"),
        ("Forma reciente", home.get("form_string", "-"),
         away.get("form_string", "-")),
    ]

    # Construir tabla en formato monospace de ancho fijo
    metric_width = 28
    home_width = max(15, len(home_name) + 2)

    lines = ["```"]
    lines.append(f"{'Métrica':<{metric_width}} {home_name[:12]:<{14}} {away_name[:12]:<{14}}")
    lines.append(f"{'-' * metric_width} {'-' * 14} {'-' * 14}")

    for label, h, a in rows:
        h_str = str(h)
        a_str = str(a)
        lines.append(f"{label:<{metric_width}} {h_str:<{14}} {a_str:<{14}}")

    lines.append("```")
    return "\n".join(lines)


def format_history_message(predictions: List[dict]) -> str:
    """Formatea el historial de predicciones anteriores."""
    if not predictions:
        return "📋 No hay predicciones guardadas todavía."

    lines = ["📋 HISTORIAL DE PREDICCIONES", ""]
    for i, pred in enumerate(predictions, start=1):
        lines.append(f"{i}. **{pred['match_description']}**")
        lines.append(f"   📅 {pred['created_at']}")
        lines.append(f"   Confianza: {pred['confidence']}")
        lines.append("")

    return "\n".join(lines)


def format_error_message(error_msg: str) -> str:
    """Formatea un mensaje de error para el usuario."""
    return f"❌ **Error**: {error_msg}"
