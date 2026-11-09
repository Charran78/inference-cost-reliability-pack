# Runbook: benchmark en H100 spot

Objetivo: ejecutar baseline y variantes optimizadas en la misma H100 y conservar evidencia suficiente para completar la tabla. La duración estimada es 3–4 horas si la instancia, descargas y modelos arrancan sin incidencias; no es una garantía de tiempo ni precio. No se incluyen datos de cliente en esta corrida pública.

## Antes de alquilar

- Reserva una única H100 de 80 GB y registra variante (SXM/PCIe), proveedor, región, tarifa spot efectiva y hora de consulta. No sustituyas esos datos por una tarifa de ejemplo.
- Comprueba Linux, Docker Compose, NVIDIA Container Toolkit, almacenamiento suficiente para las imágenes y pesos, y salida de red a Hugging Face.
- Acepta las condiciones de acceso a `meta-llama/Meta-Llama-3.1-8B-Instruct`. Mantén `HF_TOKEN` como variable de entorno/secreto; no lo escribas en archivos versionados ni en logs.
- Registra el commit evaluado (`git rev-parse HEAD`) y conserva el entorno limpio. Ejecuta las tres configuraciones sin cambiar máquina, modelos ni carga entre ellas.

## Ejecución

```bash
export HF_TOKEN=...                 # solo en el entorno de la instancia
export GPU_HOURLY_USD=...           # tarifa spot real en USD/hora
make eval-data
nvidia-smi
docker compose version
make up
docker compose --profile all ps
make bench
make report
```

`make up` inicia baseline FP16, vLLM 8B FP8, vLLM 3B FP8 y router en la misma GPU. Espera a que los servicios estén healthy antes de iniciar `make bench`. Los tres modelos comparten VRAM; si hay OOM, registra el fallo y detén la corrida. No presentes una tabla parcial como comparación equivalente.

El runner ejecuta la evaluación pública GSM8K y la carga configurada a concurrencias 1, 8, 32 y 64. La Capa B privada no se usa en esta prueba. Conserva sin editar `results/results.json` y las gráficas creadas por `make report` antes de apagar la instancia.

## Registro de evidencia

Anota junto al artefacto:

- Proveedor, tipo de H100, región, tarifa spot USD/h y fuente/URL con fecha y hora de consulta.
- Hora de inicio/fin facturada, commit, sistema operativo, Docker, NVIDIA driver, CUDA, modelo y revisión de pesos.
- Versión efectiva de vLLM (imagen configurada: `vllm/vllm-openai:v0.8.5`), parámetros de cuantización y cualquier cambio de configuración.
- Conteos de ejemplos, concurrencias y tokens por request usados. No compares corridas con parámetros distintos.
- Errores, OOM, reinicios y cualquier exclusión. Si una configuración no termina, la comparación queda incompleta.

El coste unitario se deriva como:

```text
USD por 1M tokens de salida = tarifa GPU (USD/h) * 1.000.000 / (throughput (tokens/s) * 3.600)
```

La métrica no incluye CPU, almacenamiento, red, tiempo ocioso ni el coste de un juez externo. Revisa que `hourly_gpu_cost_usd` no sea `null` antes de interpretar el coste. No inventes ni extrapoles cifras para configuraciones fallidas.

## Cierre

```bash
make down
```

Verifica que los artefactos se hayan copiado fuera de la instancia; después detén y elimina la instancia spot para evitar cargos. Antes de actualizar el README, comprueba los datos contra el JSON bruto, cita proveedor/tarifa/fecha y deja claro que son una medición de una sola máquina. El código y los modelos tienen licencias distintas: consulta cada licencia antes de redistribuir pesos.