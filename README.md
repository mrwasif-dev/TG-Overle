# Telegram Video Overlay Bot

A Telegram bot that adds an overlay to the beginning of MP4 videos.

## Features
- Adds "Family Home.mp4" overlay to videos
- Automatic positioning based on video resolution
- Fast processing with FFmpeg
- Supports videos up to 500MB
- Free for all users

## Heroku Deployment

### Method 1: Direct from GitHub (Easiest)
1. **Upload files to GitHub**
   - Create a new repository
   - Upload all files from this folder
   - Make sure `Family Home.mp4` is in `downloads/overlay/` folder

2. **Deploy to Heroku**
   - Go to [Heroku Dashboard](https://dashboard.heroku.com)
   - Click "New" → "Create new app"
   - Choose app name and region
   - Go to "Deploy" tab
   - Select "GitHub" as deployment method
   - Connect your GitHub account
   - Select your repository
   - Click "Enable Automatic Deploys"
   - Click "Deploy Branch"

3. **Configure Environment Variables**
   - Go to "Settings" tab in Heroku
   - Click "Reveal Config Vars"
   - Add the following variables:
     - `BOT_TOKEN`: Your Telegram bot token
     - `MAX_FILE_SIZE`: 500000000 (500MB)

4. **Enable Worker Dyno**
   - Go to "Resources" tab
   - Find "worker" process
   - Toggle the switch to ON

### Method 2: Heroku CLI
```bash
# Install Heroku CLI
npm install -g heroku

# Login
heroku login

# Create app
heroku create your-app-name

# Set config
heroku config:set BOT_TOKEN="your_token_here"

# Deploy
git push heroku main
