# Firebase Authentication Setup Guide for Chatly

## Overview
This guide explains how to set up Firebase Authentication for your Chatly application.

## Steps to Set Up Firebase

### 1. Create a Firebase Project
1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Click "Add project"
3. Enter your project name (e.g., "Chatly")
4. Follow the setup wizard (you can skip Google Analytics)
5. Click "Create project"

### 2. Register Your Web App
1. In the Firebase Console, click the **Web icon** (</> )
2. Enter app name "Chatly"
3. Check "Also set up Firebase Hosting" (optional)
4. Click "Register app"

### 3. Copy Your Firebase Config
After registration, you'll see a code snippet like this:
```javascript
const firebaseConfig = {
  apiKey: "YOUR_API_KEY",
  authDomain: "YOUR_PROJECT_ID.firebaseapp.com",
  projectId: "YOUR_PROJECT_ID",
  storageBucket: "YOUR_PROJECT_ID.appspot.com",
  messagingSenderId: "YOUR_MESSAGING_SENDER_ID",
  appId: "YOUR_APP_ID"
};
```

### 4. Update firebase-config.js
1. Open `firebase-config.js` in your project
2. Replace all the placeholder values with your actual Firebase credentials
3. Save the file

### 5. Enable Authentication Methods
In the Firebase Console:
1. Go to **Authentication** > **Sign-in method**
2. **Enable Email/Password**:
   - Click the Email/Password provider
   - Toggle "Enabled"
   - Click Save
3. **Enable Google Sign-In** (optional):
   - Click the Google provider
   - Toggle "Enabled"
   - Select your support email
   - Click Save

### 6. Configure OAuth Consent Screen (for Google Sign-In)
1. Go to **APIs & Services** > **OAuth consent screen**
2. Select "External" user type
3. Fill in the app details:
   - App name: "Chatly"
   - User support email: Your email
   - Developer contact: Your email
4. Click "Save and Continue"
5. Skip optional scopes
6. Skip test users (for now)
7. Go back and review your settings

### 7. Create OAuth 2.0 Credentials (for Google Sign-In)
1. Go to **APIs & Services** > **Credentials**
2. Click "Create Credentials" > "OAuth client ID"
3. Select "Web application"
4. Under "Authorized JavaScript origins", add:
   - `http://localhost:3000`
   - `http://localhost` (or your actual domain)
5. Click "Create"
6. Note your Client ID (though Firebase handles this automatically)

## Files Added

### New Files Created:
- **firebase-config.js** - Firebase configuration (edit with your credentials)
- **firebase-auth.js** - Authentication logic and handlers
- **SETUP.md** - This file

### Modified Files:
- **index.html** - Added auth modal UI and Firebase SDK imports
- **style.css** - Added authentication modal styles

## Features Implemented

**Email/Password Authentication**
- Sign up with email and password
- Sign in with existing credentials
- Password validation (minimum 6 characters)

**Google Sign-In**
- One-click Google authentication
- Automatic profile retrieval

**User Session Management**
- Persistent login (survives page refresh)
- Automatic logout
- Display user name in app

**Error Handling**
- User-friendly error messages
- Form validation

## How It Works

1. **On Page Load**: `firebase-auth.js` checks if user is logged in
2. **If Not Logged In**: Auth modal appears
3. **After Login**: Modal disappears, user name displays in sidebar
4. **Chat Features**: Only available to authenticated users
5. **Sign Out**: Click "Sign Out" button in any sidebar

## Testing

### Test Email/Password:
1. Click "Create Account"
2. Enter:
   - Name: "Test User"
   - Email: "test@example.com"
   - Password: "password123"
3. Click "Create Account"

### Test Google Sign-In:
1. Click "Sign in with Google"
2. Select your Google account
3. Authorize the app

### Test Logout:
1. Click "Sign Out" button in sidebar
2. Auth modal should appear again

## Security Notes

**Important Security Considerations:**

1. **API Key Exposure**: Your Firebase API key is visible in the client-side code. This is expected behavior - Firebase uses security rules to protect data.

2. **Firestore Security Rules**: Set up proper security rules in Firebase:
   ```javascript
   rules_version = '2';
   service cloud.firestore {
     match /databases/{database}/documents {
       match /users/{uid=**} {
         allow read, write: if request.auth.uid == uid;
       }
     }
   }
   ```

3. **Environment Variables**: In production, consider using:
   - Environment files for sensitive config
   - Backend API to handle sensitive operations
   - Cloud Functions for backend logic

## Next Steps

1. **Store User Data**: Save chat history to Firestore under user profiles
2. **Customize User Profile**: Add profile picture, bio, etc.
3. **Advanced Features**:
   - Email verification
   - Password reset
   - Social login providers (GitHub, Facebook)
   - Custom claims for admin roles

## Troubleshooting

### "Firebase is not defined"
- Make sure Firebase SDK is loaded before your scripts
- Check that `firebase-config.js` is loaded after the SDK

### Google Sign-In doesn't work
- Verify OAuth consent screen is configured
- Check authorized JavaScript origins in Google Cloud Console
- Ensure you're using the correct domain

### Auth modal won't hide
- Check browser console for JavaScript errors
- Verify Firebase credentials are correct
- Check that auth.js is properly loaded

### User state not persisting
- Clear browser cache and cookies
- Check browser's local storage settings
- Verify Firebase project settings

## Resources

- [Firebase Authentication Docs](https://firebase.google.com/docs/auth)
- [Firebase Console](https://console.firebase.google.com/)
- [Firebase Web SDK Reference](https://firebase.google.com/docs/reference/js/firebase.auth.Auth)

---

**Questions or Issues?** Check the Firebase documentation or enable debug logging in the browser console.
