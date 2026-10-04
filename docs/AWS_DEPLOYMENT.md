# AWS EC2 Production Deployment & HTTPS Guide

**Project:** Cloud-Based Biometric Authentication System  
**Architecture:** Client / Camera $\rightarrow$ HTTPS (443) $\rightarrow$ Nginx Reverse Proxy $\rightarrow$ Docker (FastAPI + InsightFace) $\rightarrow$ Supabase PostgreSQL (pgvector)  
**Target Operating System:** Ubuntu 22.04 / 24.04 LTS on AWS EC2  
**Instance Recommendation:** `t3.medium` or `c6i.large` (minimum 2 vCPUs, 4 GB RAM recommended for ONNX Runtime FaceAnalysis inference)  

---

## 1. Architectural Overview

```
                      +---------------------------------------+
                      |            Public Internet            |
                      +---------------------------------------+
                                          |
                                    HTTPS (Port 443)
                                          v
+---------------------------------------------------------------------------------+
| AWS EC2 Instance (Ubuntu 22.04 LTS)                                             |
|                                                                                 |
|   Security Group: Allow 22 (SSH), 80 (HTTP redirect), 443 (HTTPS)               |
|                                                                                 |
|   +-------------------------------------------------------------------------+   |
|   | Nginx Reverse Proxy (TLS Termination, HSTS, HTTP->HTTPS Redirection)    |   |
|   | Config: nginx/conf.d/biometric_api.conf                                 |   |
|   +-------------------------------------------------------------------------+   |
|                                     |                                           |
|                                 HTTP:8000                                       |
|                                     v                                           |
|   +-------------------------------------------------------------------------+   |
|   | Docker Container: biometric_api (Non-Root User: appuser)                |   |
|   | - FastAPI ASGI Server (Uvicorn workers = 2)                             |   |
|   | - Passive Liveness Detector (Texture + Frequency + Color PAD)           |   |
|   | - InsightFace Buffalo_L ONNX Engine (512-D Normalized Embeddings)       |   |
|   | - In-Memory Sliding Window Rate Limiter (Brute-Force Protection)        |   |
|   +-------------------------------------------------------------------------+   |
|                                     |                                           |
+-------------------------------------|-------------------------------------------+
                                      | Outbound TLS (Port 5432 / 6543)
                                      v
                      +---------------------------------------+
                      |         Supabase PostgreSQL           |
                      |   - pgvector HNSW vector_l2_ops       |
                      |   - biometric_templates table         |
                      |   - authentication_logs table         |
                      +---------------------------------------+
```

---

## 2. AWS Security Group Configuration

In the AWS EC2 Management Console, create a Security Group for the instance with the following ingress rules:

| Type | Protocol | Port Range | Source | Justification |
|---|---|---|---|---|
| **SSH** | TCP | `22` | Your IP (`x.x.x.x/32`) | Secure remote administration via SSH key pair |
| **HTTP** | TCP | `80` | `0.0.0.0/0` | ACME challenge for Let's Encrypt & HTTPS redirect |
| **HTTPS** | TCP | `443` | `0.0.0.0/0` | Secure public API and mobile client traffic |
| **Outbound** | All | All | `0.0.0.0/0` | Required for outbound access to Supabase database (`5432`/`6543`) |

> [!CAUTION]
> **DO NOT EXPOSE PORT 8000 OR 5432 IN THE AWS SECURITY GROUP INGRESS.**  
> Port 8000 is internal to the Docker network. The public internet must only enter through ports 80 and 443 managed by Nginx.

---

## 3. EC2 Host Setup & Docker Installation

### Step 3.1: Connect to your EC2 instance via SSH
```bash
ssh -i /path/to/your-key.pem ubuntu@<EC2_PUBLIC_IP>
```

### Step 3.2: Update system packages and install Docker Engine
```bash
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y ca-certificates curl gnupg lsb-release git

# Install official Docker GPG key and repository
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Enable Docker service and grant current user permissions
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER
```
*(Log out and log back in for group membership to take effect)*

---

## 4. Repository Deployment on EC2

### Step 4.1: Clone the repository on EC2
```bash
git clone https://github.com/MalharBhatt-dev/Facial-Recognition-Attendance-System.git
cd Facial-Recognition-Attendance-System
```

### Step 4.2: Configure Environment Variables (`.env`)
Create `.env` securely on the EC2 host. **Never commit `.env` into git.**

```bash
cat << 'EOF' > .env
APP_ENV=production
BIOMETRIC_STORAGE=postgres

# Supabase PostgreSQL Connection String (psycopg3 format)
# Note: Use your Supabase connection pooler URL or direct connection
DATABASE_URL=postgresql+psycopg://postgres:<YOUR_SUPABASE_PASSWORD>@db.<YOUR_SUPABASE_PROJECT_REF>.supabase.co:5432/postgres
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_POOL_TIMEOUT=30

# Biometric Engine Calibration
BIOMETRIC_MATCH_THRESHOLD=0.85
MODEL_NAME=buffalo_l
MODEL_VERSION=1.0.0
EXECUTION_PROVIDER=CPUExecutionProvider
DETECTION_THRESHOLD=0.5
ENFORCE_SINGLE_FACE_ENROLLMENT=true

# Stage 3 Liveness & Presentation Attack Detection
LIVENESS_ENABLED=true
LIVENESS_THRESHOLD=0.40
LIVENESS_METHOD=passive_texture_frequency_v1

# Stage 3 JWT Security & Administration (GENERATE A STRONG RANDOM KEY)
# Generate with: openssl rand -hex 32
JWT_SECRET_KEY=generate_and_paste_a_secure_64_character_hex_string_here
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
ADMIN_USERNAME=admin
ADMIN_PASSWORD=SetAStrongAdminPasswordHere123!

# Stage 3 Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_VERIFY_PER_MINUTE=60
RATE_LIMIT_IDENTIFY_PER_MINUTE=30
RATE_LIMIT_ENROLL_PER_MINUTE=20

# API Server Networking
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=https://yourdomain.com,https://api.yourdomain.com
LOG_LEVEL=INFO
EOF

# Lock down file permissions so only current user can read .env
chmod 600 .env
```

---

## 5. Build and Launch the Application Container

### Step 5.1: Build the hardened production Docker image
```bash
docker build -t biometric_api:latest .
```

### Step 5.2: Run the Container
```bash
docker run -d \
  --name biometric_api \
  --restart unless-stopped \
  --env-file .env \
  -p 127.0.0.1:8000:8000 \
  biometric_api:latest
```
*(Notice `-p 127.0.0.1:8000:8000` binds only to localhost, preventing direct public internet exposure)*

### Step 5.3: Verify Container Health
```bash
# Check container status
docker ps

# Query health check endpoint
curl -s http://127.0.0.1:8000/api/v1/health | jq .
```
Expected output:
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "storage_backend": "postgres",
  "database_connected": true
}
```

---

## 6. HTTPS and TLS Configuration (Nginx + Let's Encrypt Certbot)

### Step 6.1: Point DNS Domain to EC2 Elastic IP
In your DNS provider (e.g. Route 53, Cloudflare, Namecheap), create an **A Record**:
- `api.yourdomain.com` $\rightarrow$ `<YOUR_EC2_PUBLIC_ELASTIC_IP>`

### Step 6.2: Install Nginx and Certbot on Ubuntu
```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx
```

### Step 6.3: Obtain Free TLS Certificate from Let's Encrypt
```bash
sudo certbot certonly --nginx -d api.yourdomain.com
```

### Step 6.4: Configure Nginx Reverse Proxy
Copy the project's hardened Nginx configuration:
```bash
sudo cp nginx/conf.d/biometric_api.conf /etc/nginx/sites-available/biometric_api.conf
sudo sed -i 's/yourdomain.com/api.yourdomain.com/g' /etc/nginx/sites-available/biometric_api.conf
sudo ln -sf /etc/nginx/sites-available/biometric_api.conf /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test Nginx configuration syntax
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

### Step 6.5: Verify Automated Certificate Renewal
```bash
sudo certbot renew --dry-run
```

---

## 7. Operational Health Checks and Verification

From any external machine or terminal:

### 1. Test HTTPS Health Probe:
```bash
curl -i https://api.yourdomain.com/api/v1/health
```

### 2. Obtain Administrative Access Token:
```bash
curl -X POST https://api.yourdomain.com/api/v1/auth/token \
  -d "username=admin&password=SetAStrongAdminPasswordHere123!"
```
Returns:
```json
{
  "access_token": "eyJhbGciOiJIUzI1Ni...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### 3. Enroll Subject with Bearer Token:
```bash
curl -X POST https://api.yourdomain.com/api/v1/auth/enroll \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -F "user_id=USR_001" \
  -F "name=John Doe" \
  -F "image=@john_doe_portrait.jpg"
```

### 4. 1:1 Biometric Verification:
```bash
curl -X POST https://api.yourdomain.com/api/v1/auth/verify \
  -F "user_id=USR_001" \
  -F "image=@john_doe_probe.jpg"
```

### 5. 1:N Biometric Identification:
```bash
curl -X POST https://api.yourdomain.com/api/v1/auth/identify \
  -F "image=@unknown_probe.jpg"
```
