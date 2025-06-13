# LangGraph Interrupt Demo

[![LangGraph](https://img.shields.io/badge/LangGraph-Human--in--the--Loop-blue)](https://langchain-ai.github.io/langgraph/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-000000?logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A comprehensive demonstration of **LangGraph's human-in-the-loop interrupt functionality** with a modern web interface. This project showcases how to build interactive AI workflows that can pause execution, request user input, and resume processing based on user decisions.

## 🚀 Features

### Core LangGraph Interrupt Capabilities
- **Dynamic Interrupts**: Pause graph execution at any node for user input
- **State Preservation**: Maintain conversation and workflow state across interrupts
- **Resume Functionality**: Continue execution with user-provided choices
- **Multiple Interrupt Types**: Support different types of user interactions
- **Flexible Options**: Both predefined choices and free-text input support

### Technical Implementation
- **Backend**: FastAPI with LangGraph state management
- **Frontend**: Next.js with real-time UI updates
- **LLM Integration**: IBM Watson ChatWatsonx (easily swappable)
- **State Management**: Persistent conversation threading
- **Interactive UI**: Modern glassmorphism design with animations

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   Backend       │    │   LangGraph     │
│   (Next.js)     │◄──►│   (FastAPI)     │◄──►│   Workflow      │
│                 │    │                 │    │                 │
│ • Chat Interface│    │ • State Mgmt    │    │ • Node Execution│
│ • Interrupt UI  │    │ • API Endpoints │    │ • Interrupts    │
│ • Progress Bar  │    │ • Threading     │    │ • State Flow    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 📋 Prerequisites

- **Python 3.11+** (for backend)
- **Node.js 18+** (for frontend)
- **IBM Watson Account** (or modify for other LLM providers)

## 🛠️ Installation

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/langgraph-interrupt-app.git
cd langgraph-interrupt-app
```

### 2. Backend Setup
```bash
cd backend

# Create virtual environment
python -m venv langgraph-interrupt
source langgraph-interrupt/bin/activate  # On Windows: langgraph-interrupt\Scripts\activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# For development (optional)
pip install -r requirements-dev.txt

# Create environment file
cp .env.example .env
# Edit .env with your credentials (see Configuration section)
```

### 3. Frontend Setup
```bash
cd frontend

# Install dependencies
npm install

# Or with yarn
yarn install
```

## ⚙️ Configuration

Create a `.env` file in the `backend/` directory:

```env
# IBM Watson Configuration
WATSONX_URL=https://us-south.ml.cloud.ibm.com
WATSONX_API_KEY=your_watson_api_key_here
WATSONX_PROJECT_ID=your_project_id_here

# LangChain Tracing (Optional)
LANGCHAIN_API_KEY=your_langchain_api_key
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_PROJECT=your_project_name
```

### Environment Variables Explained

| Variable | Description | Required |
|----------|-------------|----------|
| `WATSONX_URL` | Watson ML service endpoint | Yes |
| `WATSONX_API_KEY` | Your IBM Watson API key | Yes |
| `WATSONX_PROJECT_ID` | Watson project identifier | Yes |
| `LANGCHAIN_*` | LangChain tracing config | No |

## 🚀 Running the Application

### Option 1: Local Development

#### Start Backend Server
```bash
cd backend
source langgraph-interrupt/bin/activate
python main.py
# Server runs on http://localhost:8000
```

#### Start Frontend Server
```bash
cd frontend
npm run dev
# Frontend runs on http://localhost:3000
```

### Option 2: Docker (Recommended for Production)

```bash
# Copy environment file
cp backend/.env.example backend/.env
# Edit backend/.env with your credentials

# Build and run with Docker Compose
docker-compose up --build

# Access the application at http://localhost:8000
```

## 📖 Understanding LangGraph Interrupts

### How Interrupts Work

1. **Node Execution**: Graph executes nodes sequentially
2. **Interrupt Trigger**: Node calls `interrupt()` function
3. **State Pause**: Execution stops, state is preserved
4. **User Interaction**: Frontend displays options to user
5. **Resume**: User choice sent back via `Command(resume=choice)`
6. **Continue**: Graph resumes with user input

### Code Example

```python
from langgraph.types import interrupt

def interactive_node(state: State) -> Dict[str, Any]:
    # Process current state
    analysis = analyze_data(state["input"])
    
    # Interrupt for user decision
    user_choice = interrupt({
        "message": "How should I proceed?",
        "options": ["option1", "option2", "option3"],
        "context": analysis
    })
    
    # Continue based on user choice
    return {
        "user_decision": user_choice,
        "next_step": determine_next_step(user_choice)
    }
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/start` | POST | Initialize new conversation thread |
| `/resume` | POST | Resume interrupted workflow |
| `/get_state/{thread_id}` | GET | Get current workflow state |

## 🎨 Customization

### Adding New Interrupt Types

1. **Create Node Function**:
```python
def custom_interrupt_node(state: YourState) -> Dict[str, Any]:
    result = interrupt("Your custom message here")
    return {"custom_field": result}
```

2. **Add to Graph**:
```python
graph_builder.add_node("custom_node", custom_interrupt_node)
graph_builder.add_edge("previous_node", "custom_node")
```

3. **Update Frontend** (optional):
```typescript
// Handle custom interrupt types in your UI
if (interruptType === "custom") {
    // Custom UI logic
}
```

### Swapping LLM Providers

Replace the Watson LLM in `backend/graph.py`:

```python
# Instead of ChatWatsonx
from langchain_openai import ChatOpenAI
# or
from langchain_anthropic import ChatAnthropic

def get_llm():
    return ChatOpenAI(model="gpt-4")  # or your preferred model
```

## 🧪 Testing

### Backend Tests
```bash
cd backend
source langgraph-interrupt/bin/activate
python -m pytest test_main.py -v
```

### Frontend Tests (Future)
```bash
cd frontend
npm test
```

### End-to-End Testing
1. Start both backend and frontend
2. Navigate to http://localhost:3000
3. Test the complete interrupt flow:
   - Start a conversation
   - Verify interrupt appears
   - Select options and resume
   - Check final response

## 🧪 Example Use Cases

This interrupt framework can be adapted for various scenarios:

- **Content Review**: Pause for human approval before publishing
- **Data Processing**: User selection of processing methods
- **Workflow Routing**: Dynamic path selection based on user input
- **Quality Control**: Human verification at critical steps
- **Configuration**: Runtime parameter adjustment
- **Error Handling**: User decision on error recovery

## 📁 Project Structure

```
langgraph-interrupt-app/
├── backend/
│   ├── main.py              # FastAPI application
│   ├── graph.py             # LangGraph workflow definition
│   ├── requirements.txt     # Python dependencies
│   ├── requirements-dev.txt # Development dependencies
│   ├── test_main.py         # Basic tests
│   ├── .env.example         # Environment template
│   └── .env                 # Environment variables (create from example)
├── frontend/
│   ├── app/
│   │   ├── page.tsx         # Main chat interface
│   │   ├── layout.tsx       # App layout
│   │   └── globals.css      # Global styles
│   ├── package.json         # Node.js dependencies
│   └── tailwind.config.js   # Tailwind configuration
├── .github/
│   └── ISSUE_TEMPLATE/      # GitHub issue templates
│       ├── bug_report.md
│       └── feature_request.md
├── .gitignore              # Git ignore rules
├── CHANGELOG.md            # Version history
├── CONTRIBUTING.md         # Contribution guidelines
├── Dockerfile              # Docker configuration
├── docker-compose.yml      # Docker Compose setup
├── LICENSE                 # MIT License
├── README.md               # This file
└── SECURITY.md             # Security policy
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Troubleshooting

### Common Issues

**Backend Issues:**
- **Import errors**: Ensure virtual environment is activated
- **Watson authentication**: Verify API keys in `.env`
- **Port conflicts**: Change port in `main.py` if needed

**Frontend Issues:**
- **Build errors**: Clear `.next` folder and rebuild
- **API connection**: Verify backend is running on correct port
- **Styling issues**: Check Tailwind CSS configuration

**LangGraph Issues:**
- **State persistence**: Ensure checkpointer is properly configured
- **Interrupt not working**: Verify `interrupt()` function usage
- **Threading errors**: Check thread_id consistency

### Debug Mode

Enable debug logging in `backend/main.py`:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 🔗 Resources

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Next.js Documentation](https://nextjs.org/docs)
- [IBM Watson Documentation](https://cloud.ibm.com/docs/watson)

## 💡 Next Steps

- [ ] Add more interrupt types (file upload, drawing, etc.)
- [ ] Implement webhook support for external interrupts
- [ ] Add workflow visualization
- [ ] Create interrupt analytics and monitoring
- [ ] Build reusable interrupt components library
