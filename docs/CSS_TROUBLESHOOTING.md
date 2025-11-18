# CSS Not Loading - Troubleshooting Guide

## 🔍 Quick Fix

If CSS is not loading, try these steps:

### 1. Restart the Flask Server
```powershell
# Stop the server (Ctrl+C) and restart
python app.py
```

### 2. Clear Browser Cache
- Press `Ctrl + Shift + Delete` (Windows) or `Cmd + Shift + Delete` (Mac)
- Clear cached images and files
- Or use `Ctrl + F5` to hard refresh the page

### 3. Check Browser Console
- Press `F12` to open Developer Tools
- Go to the "Console" tab
- Look for any errors related to CSS loading

### 4. Verify Static Files Are Being Served
Open in browser: `http://localhost:5000/static/css/custom.css`

If you see CSS content, static files are working. If you get a 404, there's an issue.

---

## 🛠️ Common Issues & Solutions

### Issue 1: Tailwind CDN Not Loading

**Symptoms:** Page looks unstyled, only HTML structure visible

**Solution:**
1. Check internet connection (Tailwind loads from CDN)
2. Check browser console for blocked resources
3. The fallback CSS (`/static/css/custom.css`) should load automatically

**Test:**
```powershell
# Test if CDN is accessible
curl https://cdn.tailwindcss.com
```

### Issue 2: Static Files Not Found (404)

**Symptoms:** Browser console shows 404 for `/static/css/custom.css`

**Solution:**
1. Verify `static/css/custom.css` exists:
   ```powershell
   Test-Path "static\css\custom.css"
   ```

2. If missing, create it:
   ```powershell
   New-Item -ItemType Directory -Path "static\css" -Force
   # Then copy/create the CSS file
   ```

3. Restart Flask server

### Issue 3: Flask Not Serving Static Files

**Symptoms:** All static files return 404

**Solution:**
1. Verify Flask configuration in `app.py`:
   ```python
   app = Flask(__name__, static_folder='static', static_url_path='/static')
   ```

2. Check if `static` directory exists in project root

3. Restart Flask server

### Issue 4: Browser Blocking External Resources

**Symptoms:** CDN resources not loading, console shows CORS or blocked errors

**Solution:**
1. Check browser security settings
2. Disable ad blockers temporarily
3. Try a different browser
4. Use the fallback CSS file instead

---

## ✅ Verification Steps

### Step 1: Check File Structure
```powershell
# Should show static directory
Get-ChildItem -Directory | Select-Object Name

# Should show CSS file
Get-ChildItem "static\css" | Select-Object Name
```

### Step 2: Test Static File Route
```powershell
# Start Flask server
python app.py

# In another terminal, test the route
curl http://localhost:5000/static/css/custom.css
```

### Step 3: Check Browser Network Tab
1. Open browser Developer Tools (F12)
2. Go to "Network" tab
3. Reload the page
4. Look for:
   - `custom.css` - should return 200 OK
   - `tailwindcss.com` - should return 200 OK
   - Any 404 errors

---

## 🔧 Manual Fix

If CSS still doesn't load:

### Option 1: Use Inline Styles
All HTML files already have inline `<style>` tags as fallback.

### Option 2: Download Tailwind Locally
1. Download Tailwind CSS
2. Place in `static/css/tailwind.css`
3. Update HTML to use local file:
   ```html
   <link rel="stylesheet" href="/static/css/tailwind.css">
   ```

### Option 3: Use CDN Alternative
Update HTML files to use a different CDN:
```html
<!-- Alternative CDN -->
<link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
```

---

## 📝 Current Setup

Your project uses:
- **Primary:** Tailwind CSS from CDN (`https://cdn.tailwindcss.com`)
- **Fallback:** Custom CSS file (`/static/css/custom.css`)
- **Inline:** Styles in `<style>` tags in each HTML file

All three should work, but if CDN fails, fallback CSS should load automatically.

---

## 🚀 Quick Test

Run this to verify everything is set up correctly:

```powershell
# 1. Check static directory exists
Test-Path "static\css\custom.css"

# 2. Start server
python app.py

# 3. Open browser to:
# http://localhost:5000/static/css/custom.css
# Should show CSS content

# 4. Open main page:
# http://localhost:5000
# Should show styled page
```

---

## 📞 Still Not Working?

1. Check Flask server logs for errors
2. Verify you're accessing `http://localhost:5000` (not `file://`)
3. Try a different browser
4. Check firewall/antivirus isn't blocking localhost
5. Verify Python and Flask are working correctly

---

**Last Updated:** November 2025

