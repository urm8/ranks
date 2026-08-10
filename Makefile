.PHONY: api-sync web-install web-build lint scraper-lint \
	api-image web-image scraper-image images push \
	template deploy scraper-deploy scraper-run status

API_DIR ?= ./api
WEB_DIR ?= ./web
SCRAPER_DIR ?= ./scraper
CHART ?= ./chart
RELEASE ?= ranks
NAMESPACE ?= ranks
KUBECONFIG ?= ./hetzner-k3s_kubeconfig.yaml

API_IMAGE ?= ghcr.io/urm8/ranks-api
WEB_IMAGE ?= ghcr.io/urm8/ranks-web
SCRAPER_IMAGE ?= ghcr.io/urm8/ranks-scraper
TAG ?= latest
# Hetzner CAX = arm64; CX = amd64. Override as needed.
PLATFORM ?= linux/arm64

PASSWORD ?=

api-sync:
	cd $(API_DIR) && uv sync

web-install:
	cd $(WEB_DIR) && pnpm install

web-build:
	cd $(WEB_DIR) && pnpm build

lint: api-sync
	cd $(API_DIR) && uv run python -c "from ranks_api.main import app; print(app.title)"
	helm lint $(CHART)

scraper-lint:
	cd $(SCRAPER_DIR) && uv sync --frozen --no-dev
	cd $(SCRAPER_DIR) && uv run scrapy list >/dev/null
	helm lint $(CHART)

api-image:
	docker build --platform $(PLATFORM) -t $(API_IMAGE):$(TAG) $(API_DIR)

web-image:
	docker build --platform $(PLATFORM) -t $(WEB_IMAGE):$(TAG) $(WEB_DIR)

scraper-image:
	docker build --platform $(PLATFORM) -t $(SCRAPER_IMAGE):$(TAG) $(SCRAPER_DIR)

images: api-image web-image scraper-image

push:
	docker push $(API_IMAGE):$(TAG)
	docker push $(WEB_IMAGE):$(TAG)
	docker push $(SCRAPER_IMAGE):$(TAG)

template:
	helm template $(RELEASE) $(CHART) --namespace $(NAMESPACE)

deploy:
	@test -n "$(PASSWORD)" || (echo "Set PASSWORD=... for ranks DB user"; exit 1)
	helm upgrade --install $(RELEASE) $(CHART) \
		--namespace $(NAMESPACE) \
		--create-namespace \
		--kubeconfig $(KUBECONFIG) \
		--set ranks.database.password=$(PASSWORD) \
		--set ranks.scraperCron.enabled=true

scraper-deploy: deploy

scraper-run:
	kubectl --kubeconfig $(KUBECONFIG) -n $(NAMESPACE) delete job $(RELEASE)-scraper-manual --ignore-not-found
	kubectl --kubeconfig $(KUBECONFIG) -n $(NAMESPACE) create job $(RELEASE)-scraper-manual \
		--from=cronjob/$(RELEASE)-scraper
	kubectl --kubeconfig $(KUBECONFIG) -n $(NAMESPACE) wait --for=condition=complete \
		job/$(RELEASE)-scraper-manual --timeout=1800s
	kubectl --kubeconfig $(KUBECONFIG) -n $(NAMESPACE) logs job/$(RELEASE)-scraper-manual

status:
	kubectl --kubeconfig $(KUBECONFIG) -n $(NAMESPACE) get deploy,svc,ingress,cronjob,pods
