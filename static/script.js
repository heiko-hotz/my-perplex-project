document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('query-form');
    const input = document.getElementById('query-input');
    const chatbox = document.getElementById('chatbox');
    const submitButton = document.getElementById('submit-button');

    // Store the current stream connection
    let eventSource = null;

    form.addEventListener('submit', (e) => {
        e.preventDefault();
        const query = input.value.trim();
        if (!query) return;

        // Display user's message immediately
        appendMessage(query, 'user-message');
        input.value = '';
        submitButton.disabled = true;

        // Start the agent interaction
        startAgentInteraction(query);
    });

    async function startAgentInteraction(query) {
        // Close any existing stream before starting a new one
        if (eventSource) {
            eventSource.close();
        }

        const appName = "ResearchTeam"; // Must match your root_agent folder name
        const userId = "user_123";
        const sessionId = "session_abc"; // Using a consistent ID for simplicity

        const streamUrl = `/run_sse`;

        const payload = {
            app_name: appName,
            user_id: userId,
            session_id: sessionId,
            new_message: {
                role: "user",
                parts: [{ "text": query }]
            },
            // Set initial state for the first message in a session
            state: { "user_question": query }
        };

        try {
            // Initiate the agent run via POST. The response is a stream.
            const response = await fetch(streamUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            // Process the streaming response
            await processStream(response.body);

        } catch (error) {
            console.error('Error initiating agent run:', error);
            appendMessage('Error: Could not connect to the agent.', 'agent-activity');
        } finally {
            submitButton.disabled = false;
        }
    }

    async function processStream(stream) {
        const reader = stream.getReader();
        const decoder = new TextDecoder();
        let agentMessageElement = null; // To hold the current agent message bubble

        while (true) {
            const { value, done } = await reader.read();
            if (done) {
                console.log('Stream finished.');
                break;
            }

            const chunk = decoder.decode(value, { stream: true });
            
            // SSE messages are separated by double newlines and start with "data: "
            const lines = chunk.split('\n\n');
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const eventData = JSON.parse(line.substring(6));
                        
                        // If it's the final response, we can stop
                        if (eventData.is_final_response) {
                             agentMessageElement = null; // Reset for the next turn
                        }

                        // Display activity messages from agents
                        if (eventData.author !== 'user' && !eventData.is_final_response) {
                            if (eventData.content && typeof eventData.content === 'string') {
                                appendMessage(eventData.content, 'agent-activity');
                            } else if (eventData.author) {
                                // Simple mapping from agent name to activity text
                                const activityText = getActivityText(eventData.author);
                                if (activityText) appendMessage(activityText, 'agent-activity');
                            }
                        }

                        // Handle the main content for the final AI message
                        if (eventData.is_final_response && eventData.content && eventData.content.parts[0].text) {
                            if (agentMessageElement) {
                                agentMessageElement.textContent += eventData.content.parts[0].text;
                            } else {
                                agentMessageElement = appendMessage(eventData.content.parts[0].text, 'agent-message');
                            }
                        }

                    } catch (e) {
                        console.error('Error parsing SSE event data:', e, "Data chunk:", line);
                    }
                }
            }
        }
    }

    function getActivityText(author) {
        const activityMap = {
            'QueryGeneratorAgent': 'Generating search queries...',
            'ResearchManager': 'Starting research...',
            'ResearcherAgent': 'Researching a topic...',
            'ReflectorAgent': 'Reflecting on findings...',
            'LoopController': 'Deciding next steps...',
            'SummarizerAgent': 'Preparing final summary...'
        };
        return activityMap[author] || null;
    }

    function appendMessage(text, className) {
        const messageElement = document.createElement('div');
        messageElement.className = `message ${className}`;
        messageElement.textContent = text;
        chatbox.appendChild(messageElement);
        // Scroll to the bottom of the chatbox
        chatbox.scrollTop = chatbox.scrollHeight;
        return messageElement;
    }
});