.PHONY: $(VERSIONS) build-% test-% test-all pqc-build pqc-test

VERSIONS = 3.11 3.12 3.13 3.14


build-%:
	docker build --build-arg PYTHON_VERSION=$* \
		-t pico_client_auth-test:$* --no-cache -f Dockerfile.test .

test-%: build-%
	docker run --rm pico_client_auth-test:$*

test-all: $(addprefix test-, $(VERSIONS))
	@echo "All versions done"

pqc-build:
	docker build -t pico_client_auth-pqc-test:latest --no-cache -f Dockerfile.pqc-test .

pqc-test: pqc-build
	docker run --rm pico_client_auth-pqc-test:latest
