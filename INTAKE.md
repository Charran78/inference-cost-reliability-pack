# Intake privado de evaluación

Este contrato recoge prompts reales del cliente para medir su caso de uso. El sector guía la etiqueta de tarea; no es una fuente para crear casos. No se construye ni publica un dataset sectorial.

## Qué manda el cliente

- 100–150 prompts reales de una ventana de tráfico acordada; objetivo recomendado: 120. No rellenar con ejemplos sintéticos.
- Un `expected_output` por prompt, revisado por una persona del dominio y respaldado por la fuente de verdad autorizada.
- Solo el contexto mínimo necesario y autorizado; no enviar documentos completos salvo permiso contractual explícito.
- Una referencia pseudónima `source_ref` que el cliente pueda resolver internamente, sin rutas ni títulos confidenciales.
- Un `task_type` y un `selection_bucket` de [`SELECTION.md`](SELECTION.md).

Entrega UTF-8 JSONL por el canal seguro acordado en `private_eval/domain_set.jsonl`, una instancia JSON por línea. No enviar la tabla de correspondencia a los prompts originales. No incluir credenciales, secretos, PII ni casos inventados para completar cuotas.

## Anonimización: checklist

1. Obtén aprobación del responsable del cliente; acuerda propósito, personas autorizadas, canal seguro y fecha de eliminación antes de exportar.
2. Copia solo las columnas necesarias. Excluye nombres, correos, teléfonos, direcciones, IDs, cuentas, tokens, claves, matrículas, IPs y datos sanitarios/financieros.
3. Sustituye entidades necesarias por marcadores estables dentro del caso, como `[PERSONA_1]` o `[EQUIPO_2]`. No uses hashes reversibles ni incluyas la tabla de correspondencia.
4. Generaliza fechas, ubicaciones y cifras raras que puedan reidentificar, preservando unidades y relaciones necesarias para resolver la tarea.
5. Revisa todas las cadenas: `prompt`, `context`, `expected_output`, `source_ref` y `tags`, incluidos fragmentos citados y JSON anidado.
6. Ejecuta `python tools/validate_intake.py private_eval/domain_set.jsonl`. Corrige los hallazgos sin copiar valores sensibles a logs, issues o PRs.
7. Revisa cada fila manualmente: el detector es una barrera de apoyo, no garantiza anonimización ni detecta todos los nombres propios.
8. Confirma la aprobación del cliente antes de transferir. No envíes datos a un juez externo sin autorización específica; prioriza un endpoint local/autohospedado.
9. Mantén archivo e informe fuera de Git, limita accesos y elimina ambos en la fecha acordada. El cliente conserva originales y tabla de correspondencia.

## Anexo técnico: schema de `domain_set.jsonl`

Cada línea debe cumplir este JSON Schema Draft 2020-12. `expected_output` puede ser texto o un objeto JSON esperado para tareas estructuradas.

```json
{
	"$schema": "https://json-schema.org/draft/2020-12/schema",
	"title": "Private domain_set.jsonl record",
	"type": "object",
	"required": ["id", "task_type", "selection_bucket", "prompt", "expected_output"],
	"properties": {
		"id": {"type": "string", "minLength": 1},
		"task_type": {
			"type": "string",
			"enum": ["information_extraction", "procedure_following", "troubleshooting", "calculation", "structured_output"]
		},
		"selection_bucket": {
			"type": "string",
			"enum": ["high_volume", "boundary_case", "current_model_failure"]
		},
		"prompt": {"type": "string", "minLength": 1},
		"expected_output": {
			"oneOf": [
				{"type": "string", "minLength": 1},
				{"type": "object", "minProperties": 1}
			]
		},
		"context": {"type": "string"},
		"source_ref": {"type": "string", "minLength": 1},
		"tags": {"type": "array", "items": {"type": "string"}}
	},
	"additionalProperties": false
}
```

`source_ref` es opcional cuando no hay fuente documental. La rúbrica por `task_type` está en [`eval/rubric_template.json`](eval/rubric_template.json); el cliente y el responsable de evaluación completan `expected_output` antes de medir.