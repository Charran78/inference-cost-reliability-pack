# Selección de la muestra privada

La muestra procede de 50–100 prompts reales del cliente dentro de una ventana acordada. El sector solo guía etiquetas `task_type`; no es fuente para inventar casos. Objetivo recomendado: N=80 casos elegibles; si solo hay 50 válidos, se reportan 50.

## Regla 60/25/15

Distribución de la muestra final, con N entre 50 y 100:

| Bucket (`selection_bucket`) | Cuota | Selección |
|---|---:|---|
| `high_volume` | 60% | Intenciones frecuentes; muestreo dentro del tráfico elegible, ponderado por su frecuencia real. |
| `boundary_case` | 25% | Prompts reales de borde: entradas parciales, umbrales, unidades, contexto largo, restricciones en conflicto o ambigüedad que el producto deba resolver. |
| `current_model_failure` | 15% | Prompts reales donde la versión actual falla, alucina, omite un requisito o devuelve formato inválido; confirmar el fallo y su criterio esperado antes del benchmark. |
| **Total** | **100%** | |

Para cada N, asigna cuotas 60/25/15 con redondeo por restos mayores; para N=80 son 48/20/12. No fabriques casos ni fuerces una cuota si no existen casos elegibles: entrega el número real y explica el desvío. Los dos últimos buckets se sobremuestrean deliberadamente; reporta métricas por bucket. La media simple no estima la calidad sobre tráfico natural. Para ese estimado, repondera por prevalencia observada en la ventana acordada.

## Tipos de tarea guía

Marca un `task_type` principal y opcionalmente tags. Son ejes transversales, no categorías de industria ni fuentes de ejemplos:

- `information_extraction`: recuperar hechos/campos de contexto entregado.
- `procedure_following`: pasos, orden, prerrequisitos, límites y seguridad.
- `troubleshooting`: interpretar síntomas y proponer verificaciones o causas respaldadas.
- `calculation`: resultados, conversiones, tolerancias, unidades y redondeo.
- `structured_output`: clasificación o transformación a esquema/campos definidos.

## Inclusión

- Prompt enviado realmente en la ventana acordada, anonimizado antes de salir del entorno del cliente.
- `expected_output` verificable, aprobado por experto del cliente y respaldado por fuente autorizada; nunca derivado de la respuesta que se evalúa.
- Caso representativo de una intención distinta dentro de su bucket; para `high_volume`, conservar la frecuencia agregada como peso.
- `boundary_case` observado en tráfico real o en un borde de producto explícitamente acordado.
- `current_model_failure` reproducible en la versión baseline fijada, con el criterio de corrección revisado.

## Exclusión

- Casos sintéticos, de benchmarks públicos, redactados para completar cuotas o fuera del alcance contratado.
- PII/secreto sin eliminar, permiso incierto o fuente que no se pueda usar en la evaluación.
- Referencia ambigua/contradictoria, no revisada o sin contexto suficiente para juzgar.
- Duplicados textuales o casi idénticos dentro de la misma intención; conservar su frecuencia como peso, no como filas repetidas.
- Fallo no reproducible o dependiente de un incidente ya corregido y ajeno a la comparación.

## Procedimiento reproducible

1. Acordar ventana, versión baseline, permisos, criterios de los tres buckets, retención y juez permitido.
2. Anonimizar según [`INTAKE.md`](INTAKE.md), etiquetar `selection_bucket` y `task_type`; registrar conteos agregados sin IDs personales.
3. Deduplicar por intención manteniendo frecuencia como peso. Seleccionar con seed acordado y guardar seed/conteos/desvíos; no guardar la correspondencia con usuarios.
4. Verificar `expected_output` con fuente autorizada y persona del dominio. Congelar antes de ejecutar; no ajustar router/prompts usando este conjunto.
5. Calibrar la rúbrica con 10 casos y hacer spot-check humano ciego de 30, balanceado entre buckets y tipos cuando sea posible. Informar acuerdo, desacuerdos y versión de rubric.
6. Reportar `n_samples`, media de rubric 1–5 por bucket y por `task_type`; incluir media simple y ponderada por tráfico por separado. Mantener datos e informe en el perímetro contractual.