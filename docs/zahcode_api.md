# ZAH CODE Apps API Documentation

## Overview

ZAH CODE is an Egyptian developer that creates wholesale mobile apps for different distributors. All apps share the same Laravel backend API structure with different base URLs.

## Apps and Base URLs

| App Name | Arabic Name | Package Name | Base URL |
|----------|-------------|--------------|----------|
| El Rabie | شركة الربيع | com.zahcode.white_shop | https://gomletalrabia.zahcode.online/api/ |
| Gomla Shoaib | جملة شعيب | com.zahcode.gomlet_shoaib | https://gomletshoaib.zahcode.online/api/ |

## Authentication

### Register
```
POST /auth/register
Content-Type: application/x-www-form-urlencoded

Parameters:
- mobile: string (Egyptian phone, e.g., "01012345678")
- password: string
- name: string
- email: string
- city: string
- address: string
- location: string
- balance: string ("0")
- longitude: string
- latitude: string
- type: string ("user")

Response:
{
  "id": 1562,
  "profile": "https://gomletalrabia.zahcode.online/admin/assets/images/profile.jpg",
  "name": "Test User",
  "mobile": "01012345678",
  "email": "test@test.com",
  "balance": "0",
  "location": "Cairo, Egypt",
  "longitude": "31.2357",
  "latitude": "30.0444",
  "type": "user",
  "status": 1,
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

### Login
```
POST /auth/login
Content-Type: application/x-www-form-urlencoded

Parameters:
- mobile: string
- password: string

Response: Same as register
```

### Check Mobile
```
POST /auth/check-mobile
Content-Type: application/x-www-form-urlencoded

Parameters:
- mobile: string

Response:
{
  "exists": true/false
}
```

## Important: Token Expiry

**CRITICAL**: JWT tokens expire VERY quickly (within seconds/minutes). The scraper must:
1. Login/register immediately before API calls
2. Use the token in the same request session
3. Re-authenticate for each scraping batch

## Endpoints

All endpoints require `Authorization: Bearer {token}` header.

### Categories
```
GET /category/all

Response: Array of categories
[
  {
    "id": 135,
    "name": "مياه غازيه",
    "image": "https://gomletalrabia.zahcode.online/public/admin/img/upload/1715189810.png",
    "created_at": "2023-02-19T06:56:38.000000Z",
    "updated_at": "2024-05-08T18:36:50.000000Z"
  }
]
```

### Subcategories
```
GET /subcategory/all

Response: Array of subcategories
[
  {
    "id": 9,
    "name": "ابو عوف",
    "image": "https://gomletalrabia.zahcode.online/admin/img/upload/1713659998.jpg",
    "category": "11-بن"
  }
]
```

### Products

#### All Products (Limited to 10)
```
GET /products/all

Note: Returns max 10 products. Use products by category for full catalog.
```

#### Products by Category (Recommended)
```
GET /products/category_id?category_id={id}

Returns all products in a category (e.g., 203 products for category 135)
```

#### Best Sellers
```
GET /products/best_seller

Returns top 30 best selling products
```

#### Offers/Discounts
```
GET /products/offers

Returns products with active offers (170 products)
```

### Product Structure
```json
{
  "id": 509,
  "description": "<p>كرتونة * 12</p>",
  "image": "https://gomletalrabia.zahcode.online/upload/images/2142-2022-08-05.jpg",
  "name": "ستينج زجاج 275 مل",
  "total_allowed_quantity": 50,
  "stock": 7880,
  "variants": [
    {
      "id": 531,
      "price": 156,
      "discounted_price": 156,
      "unit": "باكت",
      "measurement": 1,
      "quantity": 0,
      "offer": 1,
      "offer_quantity": 50
    }
  ]
}
```

### Variant Fields
| Field | Description |
|-------|-------------|
| id | Variant ID |
| price | Original price |
| discounted_price | Current selling price |
| unit | Unit name (باكت, علبة, كرتونة) |
| measurement | Unit measurement |
| quantity | Available quantity |
| offer | Has offer (0/1) |
| offer_quantity | Minimum quantity for offer |

### Sliders (Banners)
```
GET /slider/all

Response:
[
  {
    "id": 75,
    "name": "نسكفيه",
    "image": "https://gomletalrabia.zahcode.online/admin/img/upload/1765213662.jpg",
    "id_subcategory": 85
  }
]
```

## Scraping Strategy

1. **Authentication**: Register or login to get fresh token
2. **Get Categories**: Fetch all categories first
3. **Iterate Categories**: For each category, fetch products by category_id
4. **Process Products**: Extract all variants with prices
5. **Handle Offers**: Also fetch offers endpoint for discount data
6. **Token Refresh**: Re-authenticate every batch or if token expires

## Data Counts (El Rabie - Jan 2026)

| Endpoint | Count |
|----------|-------|
| Categories | 48 |
| Subcategories | 111 |
| Best Sellers | 30 |
| Offers | 170 |
| Products (via category) | 1000+ |

## Notes

- All prices are in Egyptian Pounds (EGP)
- Stock values indicate available inventory
- Products have multiple unit variants (piece, pack, carton)
- Arabic text is UTF-8 encoded
- Image URLs are direct links to product images
