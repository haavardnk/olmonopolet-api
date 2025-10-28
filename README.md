# Ølmonopolet API

[![Build](https://github.com/haavardnk/olmonopolet-api/actions/workflows/main.yml/badge.svg)](https://github.com/haavardnk/olmonopolet-api/actions/workflows/main.yml)

Backend API for Ølmonopolet - enriching Vinmonopolet's beer catalog with ratings and information from Untappd.

## Features

- Sync products from Vinmonopolet
- Match and enrich beers with Untappd data
- Track new releases and availability
- RESTful API with Django REST Framework

## Setup

```bash
git clone https://github.com/haavardnk/olmonopolet-api.git
cd olmonopolet-api
uv sync
```

### Environment Variables

```bash
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=beerdb
DATABASE_USERNAME=beer
DATABASE_PASSWORD=your-password
DJANGO_SECRET_KEY=your-secret-key
DEBUG_VALUE=1
```

### Run

```bash
cd api
uv run python manage.py migrate
uv run python manage.py runserver
```

## Development

```bash
uv run pytest
```

## License

LGPL-3.0 License - See [LICENSE](LICENSE) file for details.
