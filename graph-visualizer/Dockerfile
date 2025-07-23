FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir \
    falkordb \
    pyvis \
    networkx \
    flask \
    flask-cors

# Copy application files
COPY app.py /app/
COPY templates /app/templates/
COPY static /app/static/

# Expose port
EXPOSE 5000

# Run the Flask app
CMD ["python", "app.py"]