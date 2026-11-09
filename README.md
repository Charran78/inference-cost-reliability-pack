# Inference Cost & Reliability Pack

**Auditoría de coste de inferencia para empresas que ya tienen LLM en producción.**

Despliego, mido y entrego un informe sobre **tu** tráfico: cuánto cuesta hoy servir tus prompts, cuánto baja con cuantización FP8 + vLLM + enrutado a modelos pequeños, y qué latencia p95 y qué degradación de calidad tiene el cambio, medido sobre tus propios casos y no sobre un benchmark genérico.

**Cómo se contrata (48h, riesgo asumido por mí):**

1. Me envías 50–100 prompts reales de tu producto, anonimizados (protocolo en [`INTAKE.md`](./INTAKE.md)).
2. En 48h te devuelvo: coste actual, coste optimizado, latencia p95 antes/después y delta de calidad sobre tus casos.
3. Si el ahorro proyectado no supera el **30%**, no pagas.

**Lo que este repo demuestra (y lo que no):**

- ✅ **Metodología reproducible**: contrato de intake, regla de selección 60/25/15, rúbrica por tipo de tarea y validador que rechaza PII. Cualquiera puede clonarlo y verificar que el flujo funciona.
- ✅ **Harness ejecutable**: baseline FP16, serving vLLM FP8, router heurístico y benchmark por concurrencia. Listo para correr sobre datos de cliente.
- ❌ **No incluye cifras de rendimiento**: no publico números de un benchmark genérico porque no dicen nada sobre *tu* caso. Las cifras se producen sobre tu tráfico, dentro del contrato.

**Para técnicos que quieran verificar:** `make test` (20 tests), [`examples/`](./examples/) (formato de intake y de resultado), [`tools/validate_intake.py`](./tools/validate_intake.py) (validador con detección de PII).

**Para compradores que quieran el detalle comercial:** [`OFFER_48H.md`](./OFFER_48H.md).

---

## Qué mido y cómo

- Coste derivado por 1M tokens de salida usando la tarifa real de infraestructura acordada.
- TTFT e ITL p50/p95 para separar espera inicial y fluidez de generación.
- Throughput medido con concurrencias 1, 8, 32 y 64 bajo la misma carga.
- Delta de calidad sobre casos del cliente con respuesta esperada revisada; los casos no salen del perímetro acordado.

## El protocolo de intake

- El cliente aporta 50–100 prompts reales y anonimizados.
- Incluye `expected_output` cuando exista; solo casos con referencia validada cuentan para el delta de calidad.
- Comparte únicamente el contexto mínimo autorizado y una referencia pseudónima a la fuente.
- Revisa todas las cadenas con el validador antes de transferir.
- Detalle y checklist en [`INTAKE.md`](./INTAKE.md).

## Cómo se selecciona la muestra

La muestra se compone de 60% de prompts de alto volumen, 25% de casos límite y 15% de fallos confirmados del modelo actual. Se reportan los tres buckets por separado; no se presenta la muestra sobremuestreada como distribución natural de tráfico. Criterios en [`SELECTION.md`](./SELECTION.md).

## Cómo se puntúa la calidad

La rúbrica es por tipo de tarea: exact match cuando hay una respuesta única y escala 1–5 cuando la respuesta admite variación, con revisión humana acordada. Plantilla en [`eval/rubric_template.json`](./eval/rubric_template.json).

## Para verificarlo tú mismo

- Ejecuta `make test`: corre la suite sin GPU.
- Revisa [`examples/domain_set.example.jsonl`](./examples/domain_set.example.jsonl), [`examples/domain_set.pii_invalid.jsonl`](./examples/domain_set.pii_invalid.jsonl) y [`examples/results.example.json`](./examples/results.example.json). Son ejemplos de formato, no resultados.
- Prueba `python tools/validate_intake.py examples/domain_set.example.jsonl`; el fixture con PII debe rechazarse sin mostrar los valores detectados.
- Dependencias y versiones para herramientas locales en [`requirements.txt`](./requirements.txt).

## Limitaciones y lo que no prometo

- No publico cifras genéricas ni garantizo una mejora antes de medir tu workload y tus costes reales.
- El juez LLM está desactivado por defecto; solo se activa con autorización y endpoint acordados.
- La Capa B es privada y contractual; sus prompts y resultados no se publican ni reutilizan.

## Licencia

El código se ofrece bajo MIT en [`LICENSE`](./LICENSE). El sanity check GSM8K conserva atribución y licencia propias en [`eval/GSM8K_LICENSE`](./eval/GSM8K_LICENSE); las licencias de modelos y pesos son independientes.

## Para operar

El procedimiento interno para ejecutar y registrar una medición está en [`H100_RUNBOOK.md`](./H100_RUNBOOK.md); no contiene cifras publicables ni sustituye el acuerdo de alcance.