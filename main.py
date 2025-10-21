from fastapi import FastAPI, HTTPException, Depends, Query, Request
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from models import Product, Order
from bson import ObjectId

from google import genai
from google.genai import types
import requests
import os


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()


origins = [
    "http://localhost:5173",      # React dev server
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,        # Allow these origins
    allow_credentials=True,
    allow_methods=["*"],          # Allow all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],          # Allow all headers
)


@app.get('/')
async def root():
    return {'message': 'E-commerce API runnig'}



MONGO_URI = "mongodb+srv://thecoder4004:mathan1999@cluster0.jlwuemb.mongodb.net/mila-ecom?retryWrites=true&w=majority&appName=Cluster0"
DATABASE_NAME = "mila-ecom"

client = AsyncIOMotorClient(MONGO_URI)
db = client[DATABASE_NAME]

def get_database():
    return db

cat_map = {
    "men": ["Aromatique Gentlemen"],
    "women": ["Essencia Femme"],
    "unisex": []
}


def serialize_product(product):
    product["_id"] = str(product["_id"])
    if "category" in product and isinstance(product["category"], ObjectId):
        product["category"] = str(product["category"])
    return product

# @app.get("/product")
# async def get_products():
#     products = await db["products"].find().to_list(100)
#     return [serialize_product(p) for p in products]

import re

async def get_product(scent_type: str, max_price: float):
    """
    Fetch products filtered ONLY by max_price and categoryInfo.sub based on cat_map.
    """
    scent_type_lower = scent_type.lower()
    subcategories = cat_map.get(scent_type_lower, [])

    # Basic price filter
    products_cursor = await db["products"].find({"basePrice": {"$lte": max_price}}).to_list(200)

    # Filter by category only

    filtered = []

    for p in products_cursor:


        if p.get("categoryInfo", {}).get("sub", "") in subcategories:
            filtered.append(p)
        else:
            name = p.get("name", "").lower()

            if re.search(r"\bmen\b", name) and scent_type_lower == "men":
                filtered.append(p)
            elif re.search(r"\bwomen\b", name) and scent_type_lower == "women":
                filtered.append(p)
            elif re.search(r"\bunisex\b", name) and scent_type_lower == "unisex":
                filtered.append(p)


    
      
    return [serialize_product(p) for p in filtered]

def serialize_doc(doc):
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            doc[k] = str(v)
        elif isinstance(v, list):
            doc[k] = [serialize_doc(i) if isinstance(i, dict) else i for i in v]
        elif isinstance(v, dict):
            doc[k] = serialize_doc(v)
    return doc


# @app.get("/orders", response_model=List[Order])
# async def get_orders():
#     orders = await db["orders"].find().to_list(100)
#     return [serialize_doc(order) for order in orders]



async def get_orders(args: dict):
    args = args or {}
    order_number = args.get("order_id")
    product_name = args.get("product_name")
    full_name = args.get("name")
    if order_number:
        query = {"orderNumber": order_number}
    elif product_name and full_name:
        # Match orders where:
        # - fullName in shippingAddress OR billingAddress
        # - AND any item in items has productSnapshot.name matching product_name
        query = {
            "$and": [
                {"$or": [
                    {"shippingAddress.fullName": full_name},
                    {"billingAddress.fullName": full_name}
                ]},
                {"items": {
                    "$elemMatch": {"productSnapshot.name": {"$regex": product_name, "$options": "i"}}
                }}
            ]
        }
    # else:
    #     # If neither provided, return empty list
    #     return []

    orders_cursor = await db["orders"].find(query).to_list(100)
    return [serialize_doc(order) for order in orders_cursor]


#-------------------------------

get_product_function = {
    "name": "get_product",
    "description": "Fetches perfumes from the Milaparfum database based on scent type and budget range.",
    "parameters": {
        "type": "object",
        "properties": {
            "scent_type": {
                "type": "string",
                "description": "Type of perfume based on target audience (e.g., 'men', 'women', or 'unisex').",
                "enum": ["men", "women", "unisex"]
            },
            "max_price": {
                "type": "number",
                "description": "Maximum price of the perfume in INR."
            }
        },
        "required": ["scent_type", "max_price"]
    }
}

track_order_function = {
  "name": "track_order",
  "description": "Track the status of an order using the order number",
  "parameters": {
    "type": "object",
    "properties": {
      "order_id": {
        "type": "string",
        "description": "The unique order number"
      },
      "product_name": {
        "type": "string",
        "description": "The name of the product"
      },
      "name": {
        "type": "string",
        "description": "The name of the customer"
      }
    },
    
  }
}


instruction = """
You are a friendly and knowledgeable AI shopping assistant for the **Milaparfum** e-commerce website, which sells **non-alcoholic perfumes**.  
You can interact with the database using tools such as `get_product`, `recommend_product` and `track_order`.  

Follow these strict conversational and logical steps before calling `get_product` and `recommend_product` tool:

1. Always start by asking what type of perfume the user is looking for — for **men, women, or unisex**.  
   (Example: “Would you like to explore perfumes for men, women, or unisex options?”)

2. Once the user specifies the type, immediately ask for their **budget**.  
   Budget is always a simple number (e.g., 1000, 1500, 2000 rupees).  
   Example: “Great! What’s your budget for the perfume?”

3. After receiving the budget, **do not ask any other questions.**  
   Immediately call the `get_product` tool using the values you’ve collected:
   - `product_type` (men/women/unisex)
   - `budget`

4. Never re-ask or confirm previously given answers.  
   Do not ask more than **two questions total** (type and budget).  
   Be warm and conversational, but strictly follow the sequence above.

5. Avoid filler text like “let me confirm” or “you selected this.”  
   Just respond naturally and proceed to the next step when you have the required info.


Strict rules:
- You must collect **exactly two pieces of information**: type (men/women/unisex) and budget.  
- After that, you must immediately call the `get_product` function.
- Do not call any tool before knowing both type and budget.
- Be concise, human-like, and elegant in your tone — fitting for a perfume brand.


Example flow:
User: Hi  
Bot: Hello! Welcome to Milaparfum. Would you like to explore perfumes for men, women, or unisex options?  
User: Men  
Bot: Lovely choice! What’s your budget for the perfume?  
User: 1500  
→ (Bot calls `get_product` with {type: "men", budget: 1500})

Follow these strict conversational and logical steps before calling `track_order`.
1. If user gave the order_id , you can call the track order function.
2. If user gave the name and asked about status. You ask the user's name and then call the track_order function.

`track_order` - Tracks the status of a user's order.
   Purpose: Track the status of a user's order.
    - Parameters:
  - `order_id` (string): The unique order number. If the user provides this, it is enough to fetch the order.
  - `product_name` (string): The name of the product. Required if the user does not know the order_id.
  - `name` (string): Customer's name. Required if the user does not provide the order_id.

 Example flow:
User: What’s the status of my order 12345?
Bot: Got it! Checking your order 12345...
Bot: Your order is shipped and will be delivered by Oct 25.
--------------
User: Where is my perfume order?
Bot: Can I get your name to track the order for “Royal Musk”?
User: It’s John.
Bot: Checking your order for John and Royal Musk...
Bot: Your order is delivered today.
-------------
User: What’s my order status?
Bot: Can you tell me the product name or the order ID so I can check it for you?



"""




tools = types.Tool(function_declarations=[get_product_function,track_order_function])
config = types.GenerateContentConfig(tools=[tools],system_instruction=instruction)

API_KEY = "AIzaSyAOFKYiOtdUWd9X0dOuIMcwKCaS5Bh0wOw"

gclient = genai.Client(api_key=API_KEY)

#config = types.GenerateContentConfig(system_instruction=instruction)


conversation_history = []

class ChatRequest(BaseModel):
    user_input: str
    

@app.post("/chat/")
async def chatbot_endpoint(chat_req: ChatRequest):

    global conversation_history

    user_input = chat_req.user_input

    conversation_history.append(
        types.Content(role="user", parts=[types.Part(text=user_input)])
    )

    
    product_data = []
    msg = ""
    recommendation_data = ""

    contents = []

    contents.extend(conversation_history)

    # contents = [types.Content(
    #     role="user", parts=[types.Part(text=user_input)]
    # )
    # ]

    try:
        response = gclient.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=config
        )

        #print(response.candidates[0].content.parts[0])

        #print(response)
        tool_call = response.candidates[0].content.parts[0].function_call

        t = response.candidates[0].content.parts[0].text

        msg = t

        print(tool_call)

        print(t)

        


        if tool_call.name=="get_product":
            


            result = await get_product(tool_call.args["scent_type"],tool_call.args["max_price"])
            return result


        elif tool_call.name == 'track_order':
            print("track_order")
            result = await get_orders(tool_call.args)
            #return result[0]
            print(f"Function execution result: {result}")

    except Exception as e:
        print("wwError generating content:", e)