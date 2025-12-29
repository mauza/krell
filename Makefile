# Sarah Backend Docker Build and Deploy
# Usage:
#   make build          - Build the Docker image
#   make tag            - Tag the built image for registry
#   make push           - Push the tagged image to registry
#   make all            - Build, tag, and push in one command
#   make clean          - Remove local images

# Configuration
IMAGE_NAME = krell
REGISTRY = docker.mau.guru
VERSION ?= 0.1.0
TAG = $(REGISTRY)/$(IMAGE_NAME):$(VERSION)
LATEST_TAG = $(REGISTRY)/$(IMAGE_NAME):latest

# Phony targets (not files)
.PHONY: all build tag push clean help migrate

# Default target
all: build tag push

# Build the Docker image
build:
	@echo "Building $(IMAGE_NAME)..."
	docker build -t $(IMAGE_NAME) .
	@echo "Build complete: $(IMAGE_NAME)"

# Tag the image for the registry
tag:
	@echo "Tagging $(IMAGE_NAME) as $(TAG)..."
	docker tag $(IMAGE_NAME) $(TAG)
	docker tag $(IMAGE_NAME) $(LATEST_TAG)
	@echo "Tagged: $(TAG)"
	@echo "Tagged: $(LATEST_TAG)"

# Push the image to the registry
push:
	@echo "Pushing $(TAG)..."
	docker push $(TAG)
	@echo "Pushing $(LATEST_TAG)..."
	docker push $(LATEST_TAG)
	@echo "Push complete"

# Clean up local images
clean:
	@echo "Removing local images..."
	-docker rmi $(IMAGE_NAME) 2>/dev/null || true
	-docker rmi $(TAG) 2>/dev/null || true
	-docker rmi $(LATEST_TAG) 2>/dev/null || true
	@echo "Cleanup complete"

# Build and run locally for testing
run: build
	@echo "Running $(IMAGE_NAME) locally on port 8000..."
	docker run --rm -p 8000:8000 \
		-v $(PWD)/data:/app/data \
		--name $(IMAGE_NAME)-test \
		$(IMAGE_NAME)

# Stop the local test container
stop:
	@echo "Stopping $(IMAGE_NAME)-test..."
	docker stop $(IMAGE_NAME)-test

# Run database migrations
migrate:
	@echo "Running database migrations..."
	uv run python -m database.migrate
	@echo "Migrations complete"

# Show help
help:
	@echo "Sarah Backend Docker Makefile"
	@echo ""
	@echo "Usage:"
	@echo "  make build          - Build the Docker image"
	@echo "  make tag            - Tag the image for registry ($(REGISTRY))"
	@echo "  make push           - Push the tagged image to registry"
	@echo "  make all            - Build, tag, and push (default)"
	@echo "  make run            - Build and run locally for testing"
	@echo "  make stop           - Stop the local test container"
	@echo "  make clean          - Remove local images"
	@echo "  make migrate        - Run database migrations"
	@echo "  make help           - Show this help message"
	@echo ""
	@echo "Variables:"
	@echo "  VERSION=$(VERSION)  - Set with 'make VERSION=x.y.z <target>'"
	@echo ""
	@echo "Examples:"
	@echo "  make VERSION=0.2.0 all     - Build and push version 0.2.0"
	@echo "  make build                  - Just build locally"
	@echo "  make run                    - Build and test locally"

