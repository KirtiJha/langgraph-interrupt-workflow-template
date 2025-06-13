# Contributing to LangGraph Interrupt Workflow Template

Thank you for your interest in contributing! This project serves as a **production-ready template** for building human-in-the-loop AI workflows with LangGraph interrupts.

## 🚀 Quick Start

1. **Fork the repository**
2. **Clone your fork**
   ```bash
   git clone https://github.com/yourusername/langgraph-interrupt-workflow-template.git
   cd langgraph-interrupt-workflow-template
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

### High Priority - Template Improvements
- [ ] Additional interrupt type templates (file upload, drawing, etc.)
- [ ] More LLM provider integration examples
- [ ] Alternative workflow templates (content review, data processing, etc.)
- [ ] Enhanced UI component library
- [ ] Performance optimizations
- [ ] Better error handling patterns

### Medium Priority - Developer Experience  
- [ ] Mobile-responsive improvements
- [ ] Accessibility enhancements
- [ ] Internationalization (i18n) support
- [ ] Advanced state management patterns
- [ ] Webhook support for external interrupts
- [ ] Visual workflow designer

### Documentation & Examples
- [ ] Video tutorials for template customization
- [ ] More use case examples and templates
- [ ] API reference improvements
- [ ] Architecture deep-dive documentation
- [ ] Deployment guides for different platforms

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
