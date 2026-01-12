#!/bin/bash

# ===========================================
# Competitor Price Scraping - Deployment Script
# ===========================================
# Usage: ./deploy.sh [command]
# Commands: setup, start, stop, restart, logs, update, backup, status

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="scraping"
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.production"
BACKUP_DIR="./backups"

# Functions
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_requirements() {
    print_status "Checking requirements..."

    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Install with: curl -fsSL https://get.docker.com | sh"
        exit 1
    fi

    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        print_error "Docker Compose is not installed."
        exit 1
    fi

    print_status "Requirements OK"
}

setup() {
    print_status "Setting up production environment..."

    check_requirements

    # Create necessary directories
    mkdir -p exports static logs nginx/ssl backups

    # Check for env file
    if [ ! -f "$ENV_FILE" ]; then
        if [ -f ".env.production.example" ]; then
            print_warning "Creating $ENV_FILE from example..."
            cp .env.production.example "$ENV_FILE"
            print_warning "Please edit $ENV_FILE with your production values!"
            exit 1
        else
            print_error "$ENV_FILE not found. Create it from .env.production.example"
            exit 1
        fi
    fi

    # Build images
    print_status "Building Docker images..."
    docker-compose -f $COMPOSE_FILE build

    # Initialize database
    print_status "Starting database..."
    docker-compose -f $COMPOSE_FILE up -d db redis
    sleep 10

    # Run migrations
    print_status "Running database migrations..."
    docker-compose -f $COMPOSE_FILE run --rm api alembic upgrade head

    print_status "Setup complete! Run './deploy.sh start' to start all services."
}

start() {
    print_status "Starting all services..."
    docker-compose -f $COMPOSE_FILE up -d
    print_status "Services started!"
    status
}

start_with_nginx() {
    print_status "Starting all services with Nginx..."
    docker-compose -f $COMPOSE_FILE --profile with-nginx up -d
    print_status "Services started with Nginx!"
    status
}

stop() {
    print_status "Stopping all services..."
    docker-compose -f $COMPOSE_FILE down
    print_status "Services stopped."
}

restart() {
    print_status "Restarting services..."
    docker-compose -f $COMPOSE_FILE restart
    print_status "Services restarted!"
}

update() {
    print_status "Updating application..."

    # Pull latest code
    print_status "Pulling latest code..."
    git pull origin main 2>/dev/null || git pull origin master 2>/dev/null || print_warning "Git pull skipped"

    # Backup database before update
    backup

    # Rebuild and restart
    print_status "Rebuilding images..."
    docker-compose -f $COMPOSE_FILE build

    print_status "Running migrations..."
    docker-compose -f $COMPOSE_FILE run --rm api alembic upgrade head

    print_status "Restarting services..."
    docker-compose -f $COMPOSE_FILE up -d

    print_status "Update complete!"
}

logs() {
    SERVICE=$2
    if [ -z "$SERVICE" ]; then
        docker-compose -f $COMPOSE_FILE logs -f --tail=100
    else
        docker-compose -f $COMPOSE_FILE logs -f --tail=100 $SERVICE
    fi
}

backup() {
    print_status "Creating database backup..."

    mkdir -p $BACKUP_DIR
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="$BACKUP_DIR/db_backup_$TIMESTAMP.sql"

    docker-compose -f $COMPOSE_FILE exec -T db pg_dump -U scraper scraping_db > "$BACKUP_FILE"

    # Compress backup
    gzip "$BACKUP_FILE"

    print_status "Backup saved to ${BACKUP_FILE}.gz"

    # Keep only last 7 backups
    ls -t $BACKUP_DIR/*.gz 2>/dev/null | tail -n +8 | xargs -r rm
}

restore() {
    BACKUP_FILE=$2
    if [ -z "$BACKUP_FILE" ]; then
        print_error "Usage: ./deploy.sh restore <backup_file.sql.gz>"
        exit 1
    fi

    print_warning "This will overwrite the current database. Continue? (y/N)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        print_status "Restore cancelled."
        exit 0
    fi

    print_status "Restoring database from $BACKUP_FILE..."
    gunzip -c "$BACKUP_FILE" | docker-compose -f $COMPOSE_FILE exec -T db psql -U scraper scraping_db
    print_status "Database restored!"
}

status() {
    print_status "Service Status:"
    echo ""
    docker-compose -f $COMPOSE_FILE ps
    echo ""

    # Check API health
    print_status "API Health Check:"
    curl -s http://localhost:8000/api/v1/system/health 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "API not responding"
    echo ""
}

shell() {
    SERVICE=$2
    if [ -z "$SERVICE" ]; then
        SERVICE="api"
    fi
    docker-compose -f $COMPOSE_FILE exec $SERVICE /bin/sh
}

# CLI Help
help() {
    echo "Competitor Price Scraping - Deployment Script"
    echo ""
    echo "Usage: ./deploy.sh [command]"
    echo ""
    echo "Commands:"
    echo "  setup         - Initial setup (build images, create dirs, run migrations)"
    echo "  start         - Start all services"
    echo "  start-nginx   - Start all services including Nginx"
    echo "  stop          - Stop all services"
    echo "  restart       - Restart all services"
    echo "  update        - Pull latest code, rebuild, and restart"
    echo "  logs [svc]    - View logs (optionally for specific service)"
    echo "  backup        - Create database backup"
    echo "  restore <file>- Restore database from backup"
    echo "  status        - Show service status and health"
    echo "  shell [svc]   - Open shell in container (default: api)"
    echo "  help          - Show this help message"
    echo ""
    echo "Services: api, dashboard, worker, scheduler, db, redis, nginx"
}

# Main
case "$1" in
    setup)
        setup
        ;;
    start)
        start
        ;;
    start-nginx)
        start_with_nginx
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    update)
        update
        ;;
    logs)
        logs "$@"
        ;;
    backup)
        backup
        ;;
    restore)
        restore "$@"
        ;;
    status)
        status
        ;;
    shell)
        shell "$@"
        ;;
    help|--help|-h)
        help
        ;;
    *)
        help
        ;;
esac
