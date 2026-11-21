# EgyFreelancers 🇪🇬

**A freelance marketplace concept built to connect Egyptian freelancers with potential clients.**

EgyFreelancers is a web-based marketplace prototype designed to make discovering freelance services and connecting with local talent easier.

The project focuses on providing a dedicated space for Egyptian freelancers to showcase their work and for clients to discover services.

## Features

### For Clients
- **Explore Services:** Browse available freelance services.
- **Search & Categories:** Discover services through search and category-based browsing.
- **Service Details:** View individual service listings and their information.
- **Post Projects:** Submit project requirements for freelancers.
- **Client Dashboard:** Dedicated dashboard interface for client-side activities.

### For Freelancers
- **Freelancer Profiles:** Dedicated profile pages to showcase freelancers.
- **Publish Services:** Create and submit freelance service listings.
- **Manage Listings:** Access freelancer dashboard interfaces.
- **Showcase Work:** Present services and professional information to potential clients.

### Platform
- Separate client and freelancer experiences.
- Dedicated login and registration interfaces.
- Responsive, multi-page interface.
- Shared navigation and footer components.
- Flask-powered backend.
- SQLite database integration.
- Structured project architecture.

## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Backend development |
| Flask | Web framework |
| SQLite | Database |
| HTML5 | Page structure |
| CSS3 | Styling and layout |
| JavaScript | Frontend interactions |

## Project Structure

```text
EgyFreelancers/
│
├── egy/
│   └── Application source code
│
├── static/
│   ├── css/
│   ├── js/
│   └── images/
│
├── templates/
│   └── HTML templates
│
├── tests/
│   └── Project tests
│
├── tools/
│   └── Development utilities
│
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
└── wsgi.py
```

## Running Locally

### 1. Clone the repository

```bash
git clone https://github.com/7eeso/Egy-Freelancers.git
```

### 2. Navigate into the project

```bash
cd Egy-Freelancers
```

### 3. Install dependencies

```bash
py -m pip install -r requirements.txt
```

### 4. Configure your environment

Use `.env.example` as a reference for the required environment configuration.

Keep your actual credentials and secret keys private.

### 5. Start the application

```bash
py wsgi.py
```

Open the local address displayed by the application in your browser.

## Current Development Status

EgyFreelancers is currently an MVP/prototype.

The interface and initial marketplace workflows have been developed, but several production-level features are still under development.

**Not yet implemented:**
- Complete user authentication and authorization.
- Functional messaging between clients and freelancers.
- Payment processing and order management.
- Administrative moderation and approval interface.

Some listings and profiles use demonstration data.

## Security

- Secret keys and private configuration files are excluded from the public repository.
- Environment-specific configuration should remain private.
- Never commit credentials, database files containing private information, or sensitive user data.

## Vision

The goal of EgyFreelancers is to explore how a locally focused freelance marketplace can help Egyptian talent become more accessible to clients.

Built as a learning project with an emphasis on backend development, web architecture, and practical software engineering.

---

**Developed by 7eeso**

*EgyFreelancers — Find your next freelancer.*