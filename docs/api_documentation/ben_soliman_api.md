# Ben Soliman API Documentation

**Status: PLACEHOLDER - Update after API discovery**

## Base URL
```
https://api.bensoliman.com  # UPDATE THIS
```

## Authentication

### Login
```http
POST /api/auth/login
Content-Type: application/json
```

**Request:**
```json
{
  "mobile": "+20xxxxxxxxxx",
  "password": "user_password",
  "device_id": "abc123"
}
```

**Response:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "refresh_token_here",
  "expires_in": 3600,
  "user": {
    "id": 123,
    "name": "User Name",
    "mobile": "+20xxxxxxxxxx"
  }
}
```

## Categories

### List Categories
```http
GET /api/categories
Authorization: Bearer {token}
```

**Response:**
```json
{
  "data": [
    {
      "id": 1,
      "name": "Groceries",
      "name_ar": "بقالة",
      "image": "https://...",
      "parent_id": null,
      "order": 1
    }
  ]
}
```

## Products

### List Products
```http
GET /api/products
Authorization: Bearer {token}
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| page | int | Page number (default: 1) |
| per_page | int | Items per page (default: 20) |
| category | int | Filter by category |
| q | string | Search query |

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
      "unit": "piece",
      "min_qty": 1,
      "in_stock": true
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

## Offers/Promotions

### List Promotions
```http
GET /api/promotions
Authorization: Bearer {token}
```

**Response:**
```json
{
  "data": [
    {
      "id": 1,
      "title": "Weekly Deal",
      "title_ar": "عرض الأسبوع",
      "product_id": 123,
      "discount_type": "fixed",
      "discount_value": 10,
      "start_date": "2026-01-01",
      "end_date": "2026-01-07"
    }
  ]
}
```

## Headers Required

```
Authorization: Bearer {token}
Content-Type: application/json
Accept: application/json
Accept-Language: ar-EG
X-Device-Id: {device_id}
X-App-Version: 2.0.0
X-Platform: android
User-Agent: BenSoliman/2.0.0 (Linux; Android 13; SM-A525F) okhttp/4.10.0
```

---

**TODO: Update this file after performing API discovery**
