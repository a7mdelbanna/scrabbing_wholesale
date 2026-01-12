# Tager elSaada API Documentation

**Status: PLACEHOLDER - Update after API discovery**

## Base URL
```
https://api.tagerelsaada.com  # UPDATE THIS
```

## Authentication

### Login
```http
POST /api/v1/auth/login
Content-Type: application/json
```

**Request:**
```json
{
  "phone": "+20xxxxxxxxxx",
  "password": "user_password",
  "device_id": "abc123"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "refresh_token_here",
  "expires_in": 3600,
  "user": {
    "id": 123,
    "name": "User Name",
    "phone": "+20xxxxxxxxxx"
  }
}
```

### Refresh Token
```http
POST /api/v1/auth/refresh
Authorization: Bearer {access_token}
```

## Categories

### List Categories
```http
GET /api/v1/categories
Authorization: Bearer {access_token}
```

**Response:**
```json
{
  "data": [
    {
      "id": 1,
      "name": "Food & Beverages",
      "name_ar": "أطعمة ومشروبات",
      "image": "https://...",
      "parent_id": null,
      "sort_order": 1
    }
  ]
}
```

## Products

### List Products
```http
GET /api/v1/products
Authorization: Bearer {access_token}
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| page | int | Page number (default: 1) |
| limit | int | Items per page (default: 20) |
| category_id | int | Filter by category |
| search | string | Search query |

**Response:**
```json
{
  "data": [
    {
      "id": 123,
      "name": "Product Name",
      "name_ar": "اسم المنتج",
      "description": "...",
      "category_id": 1,
      "brand": "Brand Name",
      "sku": "SKU123",
      "barcode": "1234567890123",
      "image": "https://...",
      "price": 50.00,
      "original_price": 60.00,
      "discount_percentage": 16.67,
      "unit": "piece",
      "min_quantity": 1,
      "is_available": true
    }
  ],
  "meta": {
    "current_page": 1,
    "last_page": 50,
    "per_page": 20,
    "total": 1000
  }
}
```

### Product Detail
```http
GET /api/v1/products/{id}
Authorization: Bearer {access_token}
```

## Offers

### List Offers
```http
GET /api/v1/offers
Authorization: Bearer {access_token}
```

**Response:**
```json
{
  "data": [
    {
      "id": 1,
      "title": "Special Offer",
      "title_ar": "عرض خاص",
      "product_id": 123,
      "discount_type": "percentage",
      "discount_value": 20,
      "start_date": "2026-01-01",
      "end_date": "2026-01-31"
    }
  ]
}
```

## Headers Required

```
Authorization: Bearer {access_token}
Content-Type: application/json
Accept: application/json
Accept-Language: ar-EG
X-Device-Id: {device_id}
X-App-Version: 1.0.0
X-Platform: android
User-Agent: TagerElsaada/1.0.0 (Linux; Android 13; SM-A525F) okhttp/4.11.0
```

---

**TODO: Update this file after performing API discovery**
