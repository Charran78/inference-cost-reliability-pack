# Oferta: diagnóstico de inferencia en 48 horas

## Mensaje para enviar

**Asunto:** Medimos coste, latencia y calidad de tu endpoint de IA en 48 horas

Hola, [nombre]:

Propongo revisar un flujo de inferencia representativo de [producto/equipo] y entregarte, en 48 horas hábiles desde que estén listos los accesos y datos acordados, una comparación verificable del coste y la latencia actuales frente a una configuración optimizada.

El diagnóstico cubre un endpoint y una carga acordados. Recibes cuatro cifras principales: coste actual, coste optimizado, latencia p95 antes/después y delta de calidad sobre los casos con `expected_output` validado. El informe incluye configuración, supuestos, riesgos y qué conviene validar antes de producción.

Para empezar necesito 50–100 prompts reales y anonimizados, `expected_output` cuando exista, el contexto mínimo autorizado, versión/modelo actual, volumen aproximado, tarifa de infraestructura y condiciones de acceso. Los casos sin referencia validada pueden medir rendimiento, pero no entran en el delta de calidad. La muestra y la selección se acuerdan con el cliente.

**Cláusula de honorarios:** el ahorro proyectado se calcula como `(coste base - coste optimizado) / coste base` sobre la misma carga y volumen acordado, con las tarifas reales documentadas. Si el ahorro proyectado no supera el 30%, no pagas los honorarios de esta auditoría. Si lo supera, se factura únicamente el importe acordado por escrito antes de iniciar el trabajo.

Al cierre recibes el informe antes/después, los supuestos y artefactos para revisar las cifras, más una sesión de lectura. El trabajo se ejecuta en infraestructura controlada por el cliente (BYOD); sus datos no se copian a servidores ajenos ni se envían a un juez externo sin autorización específica.

¿Te encaja una llamada breve para definir el endpoint, la muestra y el criterio de éxito?

Un saludo,
[tu nombre]

## Límites operativos

- El plazo de 48 horas hábiles empieza cuando estén disponibles permisos, entorno del cliente, tarifa real y muestra acordada; se pausa si falta alguno.
- La implementación, cambios de producto y puesta en producción son un sprint separado.
- Los datos del cliente se ejecutan en infraestructura bajo su control (BYOD); no se suben a una H100 spot ni a otro servidor de terceros como parte de esta oferta.
- El delta de calidad medido no es garantía de calidad en producción; monitorización, rollback y garantía operativa requieren un retainer separado.
- Se reportan resultados negativos, OOM y regresiones; no se sustituyen por benchmarks de referencia.
- GSM8K es un sanity check público, no reemplaza los prompts del cliente.
- La evaluación privada no se reutiliza, publica ni incorpora al portfolio. Retención y eliminación se acuerdan antes de recibir los datos.