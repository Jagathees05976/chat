from fastapi import FastAPI, HTTPException, Depends, Query, Request
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from models import Product, Order
from bson import ObjectId
import re
from google import genai
from google.genai import types
import requests
import os
from fastapi.middleware.cors import CORSMiddleware
import json
from dotenv import load_dotenv
from pathlib import Path

app = FastAPI()

origins = [
    "http://localhost:5173",    
    "http://127.0.0.1:5173",
    "http://localhost:8001"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,        
    allow_credentials=True,
    allow_methods=["*"],      
    allow_headers=["*"],          
)

@app.get('/')
async def root():
    return {'message': 'E-commerce API runnig'}

env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

MONGO_URI = os.getenv("MONGO_URI")
database = os.getenv("DATABASE_NAME")
API_KEY = os.getenv("API_KEY")

client = AsyncIOMotorClient(MONGO_URI)
db = client[database]

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

async def get_product(scent_type: str, max_price: float):
    scent_type_lower = scent_type.lower()
    subcategories = cat_map.get(scent_type_lower, [])
    products_cursor = await db["products"].find({"basePrice": {"$lte": max_price}}).to_list(200)

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

async def get_orders(args: dict):
    args = args or {}
    order_number = args.get("order_id")
    product_name = args.get("product_name")
    full_name = args.get("name")

    query = {}
    if order_number:
        # Direct lookup by order number
        query = {"orderNumber": order_number}

    elif product_name and full_name:
        # Match by customer name and product name
        query = {
            "$and": [
                {
                    "$or": [
                        {"shippingAddress.fullName": {"$regex": full_name, "$options": "i"}},
                        {"billingAddress.fullName": {"$regex": full_name, "$options": "i"}}
                    ]
                },
                {
                    "items": {
                        "$elemMatch": {
                            "productSnapshot.name": {"$regex": product_name, "$options": "i"}
                        }
                    }
                }
            ]
        }

    orders_cursor = await db["orders"].find(query).to_list(100)
    return [serialize_doc(order) for order in orders_cursor]

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

recommend_product_function = {
    "name": "recommend_product",
    "description": "Recommend perfumes from the Milaparfum database based on scent type and budget range.",
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
   Immediately call the `get_product` or `recommend_product` tool using the values you’ve collected:
   - `product_type` (men/women/unisex)
   - `budget`

4. Never re-ask or confirm previously given answers.  
   Do not ask more than **two questions total** (type and budget).  
   Be warm and conversational, but strictly follow the sequence above.

5. Avoid filler text like “let me confirm” or “you selected this.”  
   Just respond naturally and proceed to the next step when you have the required info.

Function:
1. `get_product` - Fetches products based on filtering options provided by the user and returns the data.
2. `recommend_product` - Fetches product data and analyzes it to recommend the 4 or 5 best products. You must provide reasoning for each recommendation, highlighting price, rating, brand, features, and attributes. 

For each recommended product:
   - Explain **why** it was chosen.
   - Mention key factors such as price, rating, brand reputation, standout features, and attributes.

  At the end, return a **JSON object** in this exact format:

{
  "recommendations": [
    {
      "product_name": "Product Name 1",
      "reason": "This product offers the best balance of price and rating, with premium materials and trusted brand reputation."
    },
    {
      "product_name": "Product Name 2",
      "reason": "Affordable option with strong performance features and excellent customer reviews."
    },
    {
      "product_name": "Product Name 3",
      "reason": "High-end choice with superior build quality, advanced technology, and reliability."
    }
  ]
}

     **For product recommendations**:
   - Analyze all product details (price, rating, brand, features, attributes)
   - Recommend the top 4–5 products
   - Make sure the reasoning is **clear, concise, and data-based**.  
   - Do **not** include any text outside the JSON object.


Strict rules:
- You must collect **exactly two pieces of information**: type (men/women/unisex) and budget.  
- After that, you must immediately call the `get_product` function.
- Do not call any tool before knowing both type and budget.
- Be concise, human-like, and elegant in your tone — fitting for a perfume brand.

note: If user says "show me perfumes" call get_product function.

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

note: Use the latest user input (‘{user_input}’) as the customer’s name and call the track-order function for {item_name}.
Say the status of the order with product name and order_id

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

tools = types.Tool(function_declarations=[get_product_function,track_order_function, recommend_product_function])
config = types.GenerateContentConfig(tools=[tools],system_instruction=instruction)


gclient = genai.Client(api_key=API_KEY)
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
    recommendation_data = []
    contents = []
    contents.extend(conversation_history)

    try:
        response = gclient.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=config
        )

        tool_call = response.candidates[0].content.parts[0].function_call
        t = response.candidates[0].content.parts[0].text
        msg = t

        if tool_call.name=="get_product":           
            result = await get_product(tool_call.args["scent_type"],tool_call.args["max_price"])
            product_data = result
            msg = "Here are the asked perfumes"
            conversation_history = []

        elif tool_call.name == 'track_order':
            
            result = await get_orders(tool_call.args)
            #return result[0]
            
            function_response_part = types.Part.from_function_response(
                name=tool_call.name, response={"result":result}
            )
            contents.append(response.candidates[0].content)
            contents.append(types.Content(role="user", parts=[function_response_part]))         

            try:   
                final_response = gclient.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=config,
                )
                llm_response = final_response.candidates[0].content.parts[0].text
                msg =  llm_response
                
            except Exception as e:
                print("wwError generating content:", e)

            conversation_history = []

        elif tool_call.name == 'recommend_product':
           
            result = await get_product(tool_call.args["scent_type"],tool_call.args["max_price"])
            product_data = result

            function_response_part = types.Part.from_function_response(
                name=tool_call.name, response={"result":result}
            )

            contents.append(response.candidates[0].content)
            contents.append(types.Content(role="user", parts=[function_response_part]))

            try:
                
                final_response = gclient.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=config,
                )
                llm_response = final_response.candidates[0].content.parts[0].text               
                match = re.search(r"\{[\s\S]*\}", llm_response)
                if not match:
                    print("⚠️ No valid JSON found in model output.")
                    data = {"recommendations": []}
                else:
                    json_str = match.group(0)
                    try:
                        data = json.loads(json_str)
                    except json.JSONDecodeError as e:
                        print("⚠️ JSON decode error:", e)
                        data = {"recommendations": []}

                    recommendation_data = data.get("recommendations", [])
                
                recommended_products = [
                p for p in result
                if any(r["product_name"] == p["name"] for r in recommendation_data)]
                product_data = recommended_products
                msg = "Here are the recommended perfumes"

            except Exception as e:
                print("wwError generating content:", e)

            conversation_history = []

    except Exception as e:
        print("wwError generating content:", e)

    finally:
        return {"product_data":product_data, "msg":msg, "recommendation_data":recommendation_data}