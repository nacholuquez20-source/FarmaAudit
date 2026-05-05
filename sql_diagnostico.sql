-- Ver si hay respuestas_pregunta creadas
SELECT id, telefono_auditor, estado, timestamp_inicio, mensajes_json 
FROM respuesta_pregunta 
ORDER BY created_at DESC 
LIMIT 5;

-- Ver eventos creados hoy
SELECT id, tipo, comentario, created_at 
FROM desvio_eventos 
WHERE DATE(created_at) = CURRENT_DATE
ORDER BY created_at DESC 
LIMIT 10;
