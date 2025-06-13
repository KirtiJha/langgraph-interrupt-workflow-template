# Contributing to LangGraph Interrupt Demo

Thank you for your interest in contributing! This document provides guidelines for contributing to this project.

## 🚀 Quick Start

1. **Fork the repository**
2. **Clone your fork**
   ```bash
   git clone https://github.com/yourusername/langgraph-interrupt-app.git
   cd langgraph-interrupt-app
   ```
3. **Set up development environment** (see README.md)
4. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

## 🐛 Reporting Issues

Before creating an issue, please:
- Check if the issue already exists
- Use the issue templates when available
- Include relevant details:
  - OS and version
  - Python/Node.js versions
  - Error messages and stack traces
  - Steps to reproduce

## 💡 Suggesting Features

We welcome feature suggestions! Please:
- Check existing issues and discussions
- Clearly describe the use case
- Explain how it fits with LangGraph interrupt patterns
- Consider backward compatibility

## 🔧 Development Guidelines

### Code Style
- **Python**: Follow PEP 8, use type hints
- **TypeScript**: Follow project ESLint/Prettier config
- **Commit Messages**: Use conventional commits format
  ```
  feat: add new interrupt type for file uploads
  fix: resolve state persistence issue
  docs: update API documentation
  ```

### Backend Development
- Add type hints to all functions
- Include docstrings for public functions
- Write tests for new interrupt types
- Ensure compatibility with LangGraph patterns

### Frontend Development
- Use TypeScript strictly
- Follow existing component patterns
- Ensure responsive design
- Test interrupt UI flows

### Testing
- Add unit tests for new functionality
- Test interrupt flows end-to-end
- Verify state persistence works correctly
- Test with different LLM providers if applicable

## 📝 Pull Request Process

1. **Update documentation** for any new features
2. **Add tests** covering your changes
3. **Ensure all tests pass**
4. **Update CHANGELOG.md** if applicable
5. **Submit PR** with clear description

### PR Checklist
- [ ] Code follows project style guidelines
- [ ] Tests added/updated and passing
- [ ] Documentation updated
- [ ] No breaking changes (or clearly documented)
- [ ] Commit messages follow conventional format

## 🎯 Areas for Contribution

### High Priority
- [ ] Additional interrupt types (file upload, drawing, etc.)
- [ ] More LLM provider integrations
- [ ] Workflow visualization components
- [ ] Performance optimizations
- [ ] Better error handling

### Medium Priority
- [ ] Mobile-responsive improvements
- [ ] Accessibility enhancements
- [ ] Internationalization (i18n)
- [ ] Advanced state management
- [ ] Webhook support for external interrupts

### Documentation
- [ ] Video tutorials
- [ ] More use case examples
- [ ] API reference improvements
- [ ] Architecture deep-dive

## 🛠️ Development Setup

### Backend
```bash
cd backend
python -m venv langgraph-interrupt
source langgraph-interrupt/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt  # If you create this
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Running Tests
```bash
# Backend tests
cd backend
python -m pytest

# Frontend tests
cd frontend
npm test
```

## 📋 Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow
- Follow project guidelines

## ❓ Questions?

- Create a GitHub Discussion for general questions
- Use Issues for bugs and feature requests
- Check existing documentation first

## 🏆 Recognition

Contributors will be recognized in:
- README.md contributors section
- Release notes for significant contributions
- GitHub contributors page

Thank you for helping make this project better! 🙌
