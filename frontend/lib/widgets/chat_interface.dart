import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;
import 'package:permission_handler/permission_handler.dart';
import '../providers/patient_provider.dart';
import '../services/model_manager.dart';
import '../services/llm_service.dart';

class ChatInterface extends StatefulWidget {
  const ChatInterface({super.key});

  @override
  State<ChatInterface> createState() => _ChatInterfaceState();
}

class _ChatInterfaceState extends State<ChatInterface> {
  final TextEditingController _controller = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final stt.SpeechToText _speech = stt.SpeechToText();
  bool _isListening = false;

  Future<void> _sendMessage() async {
    final text = _controller.text.trim();
    if (text.isNotEmpty) {
      final provider = context.read<PatientProvider>();
      if (provider.isResponding) return;
      _controller.clear();
      _scrollToBottom();
      await provider.sendMessage(text);
      if (mounted) _scrollToBottom();
    }
  }

  void _scrollToBottom() {
    if (_scrollController.hasClients) {
      Future.delayed(const Duration(milliseconds: 100), () {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      });
    }
  }

  void _listen() async {
    if (!_isListening) {
      var status = await Permission.microphone.request();
      if (status != PermissionStatus.granted) {
        return;
      }

      bool available = await _speech.initialize(
        onStatus: (val) => debugPrint('onStatus: $val'),
        onError: (val) => debugPrint('onError: $val'),
      );
      if (available) {
        setState(() => _isListening = true);
        _speech.listen(
          onResult: (val) => setState(() {
            _controller.text = val.recognizedWords;
          }),
        );
      }
    } else {
      setState(() => _isListening = false);
      _speech.stop();
    }
  }

  Color _getModelStatusColor(ModelStatus status) {
    switch (status) {
      case ModelStatus.offline:
      case ModelStatus.ready:
        return Colors.green.shade600;
      case ModelStatus.checking:
      case ModelStatus.updateAvailable:
      case ModelStatus.downloading:
      case ModelStatus.verifying:
      case ModelStatus.installing:
        return Colors.orange.shade600;
      case ModelStatus.error:
        return Colors.red.shade600;
    }
  }

  String _getModelStatusText(ModelManager manager) {
    String version = manager.currentVersion;
    switch (manager.status) {
      case ModelStatus.offline:
        return "AI Model $version - Offline";
      case ModelStatus.ready:
        return "AI Model $version - Ready";
      case ModelStatus.checking:
        return "AI Model $version - Checking for updates...";
      case ModelStatus.updateAvailable:
        return "AI Model $version - Update Available";
      case ModelStatus.downloading:
        return "AI Model $version - Downloading ${manager.downloadProgress}";
      case ModelStatus.verifying:
        return "AI Model $version - Verifying...";
      case ModelStatus.installing:
        return "AI Model $version - Installing...";
      case ModelStatus.error:
        return "AI Model $version - Update Error (Rolled back)";
    }
  }

  Widget _buildMessagesList(PatientProvider provider) {
    final messages = provider.messages;
    if (messages.isEmpty) {
      return const Center(
        child: Text("Type a command or question to begin. (Offline Mode)"),
      );
    }
    return ListView.builder(
      controller: _scrollController,
      padding: const EdgeInsets.all(16),
      itemCount: messages.length,
      itemBuilder: (context, index) {
        final msg = messages[index];
        final isUser = msg.role == 'user';
        return Align(
          alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
          child: Container(
            margin: const EdgeInsets.only(bottom: 8),
            child: Column(
              crossAxisAlignment: isUser
                  ? CrossAxisAlignment.end
                  : CrossAxisAlignment.start,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 12,
                  ),
                  decoration: BoxDecoration(
                    gradient: isUser
                        ? const LinearGradient(
                            colors: [Color(0xFF2196F3), Color(0xFF1976D2)],
                            begin: Alignment.topLeft,
                            end: Alignment.bottomRight,
                          )
                        : null,
                    color: isUser ? null : Theme.of(context).cardColor,
                    borderRadius: BorderRadius.only(
                      topLeft: const Radius.circular(20),
                      topRight: const Radius.circular(20),
                      bottomLeft: isUser
                          ? const Radius.circular(20)
                          : const Radius.circular(4),
                      bottomRight: isUser
                          ? const Radius.circular(4)
                          : const Radius.circular(20),
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withValues(alpha: 0.05),
                        blurRadius: 8,
                        offset: const Offset(0, 4),
                      ),
                    ],
                  ),
                  child: Text(
                    msg.content,
                    style: TextStyle(
                      color: isUser
                          ? Colors.white
                          : Theme.of(context).textTheme.bodyLarge?.color,
                      height: 1.4,
                      fontSize: 15,
                    ),
                  ),
                ),
                if (!isUser) // Add 'Correct AI' button for assistant messages
                  TextButton.icon(
                    onPressed: () {
                      String lastUserMsg = "Unknown context";
                      for (int i = index - 1; i >= 0; i--) {
                        if (messages[i].role == 'user') {
                          lastUserMsg = messages[i].content;
                          break;
                        }
                      }
                      _showFeedbackDialog(context, lastUserMsg);
                    },
                    icon: const Icon(Icons.thumb_down, size: 14),
                    label: const Text(
                      "Correct AI",
                      style: TextStyle(fontSize: 12),
                    ),
                  ),
              ],
            ),
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Expanded(
          child: Consumer2<PatientProvider, ModelManager>(
            builder: (context, provider, modelManager, child) {
              final llmService = context.watch<LlmService>();
              return Column(
                children: [
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(8),
                    color: _getModelStatusColor(modelManager.status),
                    child: Text(
                      _getModelStatusText(modelManager),
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                        color: Colors.white,
                      ),
                    ),
                  ),
                  if (llmService.isModelInstalled)
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(4),
                      color: llmService.errorMessage != null
                          ? Colors.red
                          : (llmService.isReady
                                ? Colors.blue.shade800
                                : Colors.orange),
                      child: Text(
                        llmService.errorMessage ?? llmService.statusMessage,
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                          fontSize: 11,
                          color: Colors.white,
                        ),
                      ),
                    ),
                  Expanded(child: _buildMessagesList(provider)),
                ],
              );
            },
          ),
        ),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: Theme.of(
              context,
            ).scaffoldBackgroundColor.withValues(alpha: 0.9),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.05),
                blurRadius: 10,
                offset: const Offset(0, -5),
              ),
            ],
          ),
          child: SafeArea(
            child: Row(
              children: [
                Container(
                  decoration: BoxDecoration(
                    color: _isListening
                        ? Colors.red.withValues(alpha: 0.1)
                        : Colors.blue.withValues(alpha: 0.1),
                    shape: BoxShape.circle,
                  ),
                  child: IconButton(
                    icon: Icon(
                      _isListening ? Icons.mic : Icons.mic_none,
                      color: _isListening ? Colors.red : Colors.blue,
                    ),
                    onPressed: _listen,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextField(
                    controller: _controller,
                    decoration: InputDecoration(
                      hintText: 'e.g. "Record BP 120/80" or "Summarize"',
                      filled: true,
                      fillColor: Theme.of(context).cardColor,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(24),
                        borderSide: BorderSide.none,
                      ),
                      contentPadding: const EdgeInsets.symmetric(
                        horizontal: 20,
                        vertical: 14,
                      ),
                    ),
                    onSubmitted: (_) => _sendMessage(),
                  ),
                ),
                const SizedBox(width: 12),
                Container(
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      colors: [Color(0xFF2196F3), Color(0xFF1976D2)],
                    ),
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: Colors.blue.withValues(alpha: 0.3),
                        blurRadius: 8,
                        offset: const Offset(0, 4),
                      ),
                    ],
                  ),
                  child: IconButton(
                    icon: const Icon(Icons.send, color: Colors.white, size: 20),
                    onPressed: context.watch<PatientProvider>().isResponding
                        ? null
                        : _sendMessage,
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  void _showFeedbackDialog(BuildContext context, String lastUserMsg) {
    final typeController = TextEditingController(text: 'Intent');
    final labelController = TextEditingController();

    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('Local Offline Feedback'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  "Correcting AI for: \"$lastUserMsg\"",
                  style: const TextStyle(fontStyle: FontStyle.italic),
                ),
                const SizedBox(height: 16),
                DropdownButtonFormField<String>(
                  initialValue: 'Intent',
                  items: const [
                    DropdownMenuItem(
                      value: 'Intent',
                      child: Text('Correct Intent'),
                    ),
                    DropdownMenuItem(
                      value: 'NER',
                      child: Text('Correct Entity (NER)'),
                    ),
                  ],
                  onChanged: (val) {
                    typeController.text = val ?? 'Intent';
                  },
                  decoration: const InputDecoration(labelText: 'Feedback Type'),
                ),
                TextField(
                  controller: labelController,
                  decoration: const InputDecoration(
                    labelText: 'Correct Label',
                    hintText: 'e.g. RECORD_VITALS or VITAL_HR',
                  ),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel'),
            ),
            ElevatedButton(
              onPressed: () async {
                final api = context.read<PatientProvider>().apiService;
                bool success = false;
                if (typeController.text == 'Intent') {
                  success = await api.submitIntentFeedback(
                    lastUserMsg,
                    labelController.text,
                  );
                } else {
                  success = await api.submitNerFeedback(
                    lastUserMsg,
                    labelController.text,
                    0,
                    lastUserMsg.length,
                  );
                }

                if (context.mounted) {
                  Navigator.pop(context);
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text(
                        success
                            ? 'Feedback Queued Locally!'
                            : 'Failed to save feedback',
                      ),
                    ),
                  );
                }
              },
              child: const Text('Save Local Feedback'),
            ),
          ],
        );
      },
    );
  }
}
