def get_bot_response(text: str) -> str:
    text = (text or "").lower().strip()

    if text in ["hola", "ola", "buenas", "hey", "hi"]:
        return (
            "¡Hola! Soy Music Bot 🎵\n\n"
            "Puedo ayudarte con:\n"
            "1. Próximos eventos\n"
            "2. Contrataciones\n"
            "3. Contacto\n\n"
            "Escribe: eventos, precio o contacto."
        )

    if any(word in text for word in ["evento", "eventos", "concierto", "conciertos", "presentacion", "presentación"]):
        return (
            "🎤 Próximos eventos:\n\n"
            "Por ahora estamos actualizando la agenda.\n"
            "Muy pronto podrás consultar fechas disponibles aquí."
        )

    if any(word in text for word in ["precio", "costo", "cotizacion", "cotización", "contratar", "contrataciones"]):
        return (
            "💰 Para contrataciones, indícanos:\n\n"
            "- Fecha del evento\n"
            "- Distrito o ciudad\n"
            "- Tipo de evento\n"
            "- Duración aproximada\n\n"
            "Un encargado te responderá con la cotización."
        )

    if any(word in text for word in ["contacto", "telefono", "teléfono", "llamar", "whatsapp"]):
        return (
            "📞 Puedes dejarnos tus datos por aquí y un encargado se comunicará contigo."
        )

    return (
        "No entendí completamente tu mensaje 🤔\n\n"
        "Puedes escribir:\n"
        "- hola\n"
        "- eventos\n"
        "- precio\n"
        "- contacto"
    )