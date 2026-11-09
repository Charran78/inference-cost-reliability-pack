.PHONY: eval-data validate-intake up down bench report

DOMAIN_DATASET ?= private_eval/domain_set.jsonl

eval-data:
	python eval/build_gsm8k_subset.py

validate-intake:
	python tools/validate_intake.py $(DOMAIN_DATASET)

up: eval-data
	docker compose --profile all up -d --build baseline vllm-large vllm-small router

down:
	docker compose --profile all down

bench: eval-data
	docker compose --profile all run --rm benchmark

report:
	docker compose --profile all run --rm --entrypoint python benchmark /app/bench/plot.py --results /results/results.json