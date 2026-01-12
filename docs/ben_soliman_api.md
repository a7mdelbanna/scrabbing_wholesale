# Ben Soliman API Documentation

## Discovery Date
2026-01-12

## Base URLs
- Primary: `http://41.65.168.38:8001/customer_app/api/v2/`
- Secondary: `http://37.148.206.212:5005/customer_app/api/v2/`
- Images: `http://37.148.206.212/Icons/`

## Server Info
- Framework: FastAPI (uvicorn)
- Response Format: JSON (gzip compressed)

## Authentication

### Login
```
POST /customer_app/api/v2/login?is_reset_password=false
Content-Type: application/json

{"Mob":"<phone_number>","Password":"<password>"}
```

**Response:** Returns JWT token with very long expiry (~10 years)

**JWT Payload:**
```json
{
  "sub": "customer_id",
  "exp": 2083538489,
  "iat": 1768178489
}
```

## Required Headers
```
user-agent: Dart/3.9 (dart:io)
accept-language: ar
accept-encoding: gzip
host: 41.65.168.38:8001
authorization: Bearer <jwt_token>
os: android
```

---

## Verified Endpoints

### Categories
```
GET /customer_app/api/v2/categories?domain_id=2
```
**Response:**
```json
{
  "categories": [
    {
      "category_Id": 5,
      "Name": "سكر و دقيق و ارز",
      "ImageName": "العاصم_والاسطورة.png",
      "Banners": [],
      "IsSpecial": false
    }
  ]
}
```

### Items (Products)
```
GET /customer_app/api/v2/items?domain_id=2
GET /customer_app/api/v2/items?domain_id=2&category_id=5
```
**Response:**
```json
{
  "data": [
    {
      "ItemCode": 4020117,
      "Name": "فول مدشوش الزعيم استرالي 25 كجم",
      "SellPrice": 850.0,
      "ItemPrice": 850.0,
      "Balance": 0.0,
      "ImageName": "فول-مدشوش.png",
      "CategoryCode": 6,
      "BrandId": 1206,
      "BarCode": null,
      "Description": "فول مدشوش الزعيم استرالي  25 كجم",
      "u_codes": [
        {
          "U_Code": 7,
          "U_Name": "شيكارة",
          "U_Balance": 0,
          "Factor": 1
        }
      ],
      "Offers": [],
      "MinimumQuantity": 0,
      "Coins": 0,
      "Stars": 0,
      "IsFav": false
    }
  ]
}
```

### Brands
```
GET /customer_app/api/v2/brands?domain_id=2
```
**Response:**
```json
{
  "Brands": [
    {
      "Brand_Id": 17,
      "Name": "المراعي",
      "ImageName": "1_17.png",
      "HasOffers": false,
      "Banners": []
    }
  ]
}
```

### Home Page
```
GET /customer_app/api/v2/home?domain_id=2
```
**Response:**
```json
{
  "sections": [
    {
      "id": 2,
      "title": "إختصاراتك",
      "type_id": 2,
      "type_name": "Shortcuts Section",
      "body": [...]
    }
  ]
}
```

### Hero Banner
```
GET /customer_app/api/v2/hero_banner?domain_id=2
```
**Response:**
```json
{
  "HeroBanner": [
    {
      "id": 1462,
      "banner_image": "حلاوة_البوادي.jpg",
      "ids": [14030105, ...]
    }
  ]
}
```

---

## Field Mappings

### Product Fields
| API Field | Description | Type |
|-----------|-------------|------|
| ItemCode | Product ID | int |
| Name | Product name (Arabic) | string |
| SellPrice | Current selling price | float |
| ItemPrice | Original price | float |
| Balance | Stock quantity | float |
| ImageName | Image filename | string |
| CategoryCode | Category ID | int |
| BrandId | Brand ID | int |
| BarCode | Barcode | string |
| Description | Product description | string |
| u_codes | Unit information | array |
| Offers | Active offers | array |
| MinimumQuantity | Minimum order qty | int |

### Category Fields
| API Field | Description | Type |
|-----------|-------------|------|
| category_Id | Category ID | int |
| Name | Category name (Arabic) | string |
| ImageName | Image filename | string |
| IsSpecial | Special category flag | bool |
| Banners | Associated banners | array |

### Brand Fields
| API Field | Description | Type |
|-----------|-------------|------|
| Brand_Id | Brand ID | int |
| Name | Brand name (Arabic) | string |
| ImageName | Image filename | string |
| HasOffers | Has active offers | bool |

---

## Notes
- `domain_id=2` is the main Cairo/Giza region
- Image URLs: `http://37.148.206.212/Icons/{ImageName}`
- All product names and descriptions are in Arabic
- JWT tokens have very long expiry (~10 years)
- Prices are in Egyptian Pounds (EGP)
