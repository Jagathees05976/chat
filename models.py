from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from bson import ObjectId
from datetime import datetime

class CategoryInfo(BaseModel):
    parent: Optional[str] = None
    sub: Optional[str] = None

class MediaItem(BaseModel):
    url: Optional[str] = None
    alt: Optional[str] = None

class Product(BaseModel):
    id: Optional[str] = Field(alias="_id")
    name: str
    sku: Optional[str] = None
    description: Optional[str] = None
    basePrice: Optional[float] = 0.0
    stock: Optional[int] = 0
    category: Optional[str] = None  
    categoryInfo: Optional[CategoryInfo] = None
    media: Optional[List[MediaItem]] = []
    tags: Optional[List[str]] = []
    isActive: Optional[bool] = True
    sizes: Optional[List[str]] = []
    discountPercentage: Optional[float] = 0.0
    isFeatured: Optional[bool] = False
    attributes: Optional[List[Dict[str, Any]]] = []  
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None
    __v: Optional[int] = None

    class Config:
        allow_population_by_field_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }

class Address(BaseModel):
    addressType: Optional[str] = None
    fullName: Optional[str] = None
    phone: Optional[str] = None
    pincode: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    street: Optional[str] = None

class ShippingMethod(BaseModel):
    provider: Optional[str] = None
    serviceName: Optional[str] = None
    cost: Optional[float] = None
    estimatedDelivery: Optional[str] = None
    trackingNumber: Optional[str] = None
    trackingUrl: Optional[str] = None

class PaymentDetails(BaseModel):
    method: Optional[str] = None
    status: Optional[str] = None
    provider: Optional[str] = None
    methodType: Optional[str] = None
    paymentId: Optional[str] = None
    amountPaid: Optional[float] = None
    currency: Optional[str] = None
    gatewayResponse: Optional[Any] = None

class Totals(BaseModel):
    itemsSubtotal: Optional[float] = None
    cartDiscountAmount: Optional[float] = None
    shippingCost: Optional[float] = None
    additionalFees: Optional[float] = None
    checkoutDiscountAmount: Optional[float] = None
    grandTotal: Optional[float] = None

class CancellationDetails(BaseModel):
    isStockRestocked: Optional[bool] = None

class Metadata(BaseModel):
    cartLastUpdatedAt: Optional[datetime] = None
    errorDetails: Optional[str] = None

class Order(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    user: Optional[str] = None
    checkoutId: Optional[str] = None
    items: Optional[List[Any]] = None
    shippingAddress: Optional[Address] = None
    billingAddress: Optional[Address] = None
    isBillingSameAsShipping: Optional[bool] = None
    shippingMethod: Optional[ShippingMethod] = None
    paymentDetails: Optional[PaymentDetails] = None
    totals: Optional[Totals] = None
    status: Optional[str] = None
    cancellationDetails: Optional[CancellationDetails] = None
    metadata: Optional[Metadata] = None
    statusHistory: Optional[List[Any]] = None
    refunds: Optional[List[Any]] = None
    orderNumber: Optional[str] = None
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {datetime: lambda v: v.isoformat()}
