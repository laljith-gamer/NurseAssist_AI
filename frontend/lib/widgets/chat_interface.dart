import 'dart:ui';
import 'chat_history_drawer.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;
import 'package:permission_handler/permission_handler.dart';
import '../providers/patient_provider.dart';
import '../providers/settings_provider.dart';
import '../services/model_manager.dart';

import '../services/telemetry_service.dart';
import '../models/types.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';

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

  /// Tracks per-message label verdicts: messageId -> {label: true/false/null}.
  /// true = accepted, false = dismissed, null = not yet acted on.
  final Map<String, Map<String, bool?>> _labelVerdicts = {};

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
          child:
              Container(
                    margin: const EdgeInsets.only(bottom: 8),
                    child: Column(
                      crossAxisAlignment: isUser
                          ? CrossAxisAlignment.end
                          : CrossAxisAlignment.start,
                      children: [
                        GestureDetector(
                          onLongPress: () => _showMessageOptions(context, msg),
                          child: ClipRRect(
                          borderRadius: BorderRadius.only(
                            topLeft: const Radius.circular(24),
                            topRight: const Radius.circular(24),
                            bottomLeft: isUser
                                ? const Radius.circular(24)
                                : const Radius.circular(8),
                            bottomRight: isUser
                                ? const Radius.circular(8)
                                : const Radius.circular(24),
                          ),
                          child: BackdropFilter(
                            filter: isUser
                                ? ImageFilter.blur(sigmaX: 0, sigmaY: 0)
                                : ImageFilter.blur(sigmaX: 10, sigmaY: 10),
                            child: Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 20,
                                vertical: 14,
                              ),
                              decoration: BoxDecoration(
                                gradient: isUser
                                    ? const LinearGradient(
                                        colors: [
                                          Color(0xFF06B6D4),
                                          Color(0xFF3B82F6),
                                        ], // Vibrant cyan to blue
                                        begin: Alignment.topLeft,
                                        end: Alignment.bottomRight,
                                      )
                                    : null,
                                color: isUser
                                    ? null
                                    : (Theme.of(context).brightness ==
                                              Brightness.dark
                                          ? const Color(
                                              0xFF1E293B,
                                            ).withValues(alpha: 0.6)
                                          : Colors.white.withValues(
                                              alpha: 0.8,
                                            )),
                                border: isUser
                                    ? null
                                    : Border.all(
                                        color:
                                            Theme.of(context).brightness ==
                                                Brightness.dark
                                            ? Colors.white.withValues(
                                                alpha: 0.1,
                                              )
                                            : Colors.black.withValues(
                                                alpha: 0.05,
                                              ),
                                        width: 1,
                                      ),
                              ),
                              child: MarkdownBody(
                                data: msg.content,
                                styleSheet: MarkdownStyleSheet(
                                  p: TextStyle(
                                    color: isUser
                                        ? Colors.white
                                        : Theme.of(
                                            context,
                                          ).textTheme.bodyLarge?.color,
                                    height: 1.5,
                                    fontSize: 15,
                                    letterSpacing: 0.2,
                                  ),
                                  strong: TextStyle(
                                    color: isUser
                                        ? Colors.white
                                        : Theme.of(context).textTheme.bodyLarge?.color,
                                    fontWeight: FontWeight.bold,
                                  ),
                                  listBullet: TextStyle(
                                    color: isUser
                                        ? Colors.white
                                        : Theme.of(context).textTheme.bodyLarge?.color,
                                  ),
                                ),
                              ),
                            ),
                          ),
                        ),
                        if (!isUser && msg.observationHints.isNotEmpty)
                          _buildObservationChips(msg),
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
                  )
                  .animate()
                  .fadeIn(duration: 300.ms)
                  .slideY(
                    begin: 0.2,
                    end: 0,
                    duration: 300.ms,
                    curve: Curves.easeOut,
                  ),
        );
      },
    );
  }

  Widget _buildProposalCard(PatientProvider provider) {
    final proposal = provider.pendingProposal!;
    final colorScheme = Theme.of(context).colorScheme;
    return Container(
          width: double.infinity,
          margin: const EdgeInsets.fromLTRB(16, 4, 16, 8),
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: colorScheme.primaryContainer,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: colorScheme.primary.withValues(alpha: 0.35),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(Icons.fact_check_outlined, color: colorScheme.primary),
                  const SizedBox(width: 8),
                  Text(
                    'Review before charting',
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.w700,
                      color: colorScheme.onPrimaryContainer,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                'Patient: ${proposal.patientName}',
                style: TextStyle(color: colorScheme.onPrimaryContainer),
              ),
              const SizedBox(height: 4),
              Text(
                proposal.summary,
                style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                  fontWeight: FontWeight.w600,
                  color: colorScheme.onPrimaryContainer,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                'Interpreted by ${proposal.interpreter}. Verify against the patient and source before saving.',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: colorScheme.onPrimaryContainer,
                ),
              ),
              const SizedBox(height: 10),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton(
                    onPressed: provider.isResponding
                        ? null
                        : () async {
                            await provider.discardPendingProposal();
                            if (mounted) _scrollToBottom();
                          },
                    child: const Text('Discard'),
                  ),
                  const SizedBox(width: 8),
                  FilledButton.icon(
                    onPressed: provider.isResponding
                        ? null
                        : () async {
                            await provider.confirmPendingProposal();
                            if (mounted) _scrollToBottom();
                          },
                    icon: const Icon(Icons.save_outlined),
                    label: const Text('Confirm & Save'),
                  ),
                ],
              ),
            ],
          ),
        )
        .animate()
        .fadeIn(duration: 400.ms)
        .slideY(begin: 0.1, end: 0, duration: 400.ms, curve: Curves.easeOut);
  }

  Widget _buildChatSessionBar(PatientProvider provider) {
    final session = provider.activeChatSession;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      child: Row(
        children: [
          const Icon(Icons.forum_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              session?.title ?? 'New chat',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
          ),
          IconButton(
            tooltip: 'Chat history',
            icon: const Icon(Icons.history_outlined),
            onPressed: provider.isResponding
                ? null
                : () => _showChatHistory(context, provider),
          ),
          // Premium Glassy iPhone-style New Chat button
          ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
              child: Container(
                decoration: BoxDecoration(
                  color: Theme.of(context).brightness == Brightness.dark
                      ? Colors.white.withValues(alpha: 0.1)
                      : Colors.black.withValues(alpha: 0.05),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(
                    color: Theme.of(context).brightness == Brightness.dark
                        ? Colors.white.withValues(alpha: 0.2)
                        : Colors.white.withValues(alpha: 0.5),
                  ),
                ),
                child: Material(
                  color: Colors.transparent,
                  child: InkWell(
                    onTap: provider.isResponding
                        ? null
                        : () async {
                            await provider.startNewChat();
                            if (mounted) _scrollToBottom();
                          },
                    child: Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 8,
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            Icons.chat_bubble_outline_rounded,
                            size: 18,
                            color: Theme.of(context).colorScheme.primary,
                          ),
                          const SizedBox(width: 6),
                          Text(
                            'New Chat',
                            style: TextStyle(
                              fontWeight: FontWeight.w600,
                              fontSize: 13,
                              color: Theme.of(context).colorScheme.primary,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _showChatHistory(
    BuildContext context,
    PatientProvider provider,
  ) {
    return showGeneralDialog(
      context: context,
      barrierDismissible: true,
      barrierLabel: 'Dismiss',
      barrierColor: Colors.black54,
      transitionDuration: const Duration(milliseconds: 300),
      pageBuilder: (context, animation, secondaryAnimation) {
        return ChatHistoryDrawer(
          onChatSelected: () {
            if (mounted) _scrollToBottom();
          },
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
              return Column(
                children: [
                  _buildChatSessionBar(provider),

                  Expanded(child: _buildMessagesList(provider)),
                  if (provider.isResponding)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 8.0),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const SizedBox(
                            width: 16, 
                            height: 16, 
                            child: CircularProgressIndicator(strokeWidth: 2)
                          ),
                          const SizedBox(width: 8),
                          Text(
                            "AI is thinking...", 
                            style: TextStyle(
                              color: Theme.of(context).colorScheme.primary, 
                              fontStyle: FontStyle.italic,
                            )
                          ),
                        ],
                      ),
                    ).animate().fadeIn(duration: 200.ms),
                  if (provider.pendingProposal != null)
                    _buildProposalCard(provider),
                ],
              );
            },
          ),
        ),
        SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
            child: Row(
              children: [
                Container(
                  decoration: BoxDecoration(
                    color: _isListening
                        ? Colors.red.withValues(alpha: 0.1)
                        : (Theme.of(context).brightness == Brightness.dark
                              ? Colors.white.withValues(alpha: 0.1)
                              : Colors.black.withValues(alpha: 0.05)),
                    shape: BoxShape.circle,
                  ),
                  child: IconButton(
                    icon: Icon(
                      _isListening ? Icons.mic : Icons.mic_none,
                      color: _isListening
                          ? Colors.red
                          : (Theme.of(context).brightness == Brightness.dark
                                ? Colors.white70
                                : Colors.black54),
                    ),
                    onPressed: _listen,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Container(
                    decoration: BoxDecoration(
                      color: Theme.of(context).brightness == Brightness.dark
                          ? const Color(0xFF1E293B)
                          : Colors.grey.shade100,
                      borderRadius: BorderRadius.circular(24),
                      border: Border.all(
                        color: Theme.of(context).brightness == Brightness.dark
                            ? Colors.white.withValues(alpha: 0.1)
                            : Colors.black.withValues(alpha: 0.05),
                      ),
                    ),
                    child: Row(
                      children: [
                        Expanded(
                          child: TextField(
                            controller: _controller,
                            style: TextStyle(
                              color:
                                  Theme.of(context).brightness ==
                                      Brightness.dark
                                  ? Colors.white
                                  : Colors.black87,
                            ),
                            decoration: InputDecoration(
                              hintText: 'e.g. "Record BP 120/80"...',
                              hintStyle: TextStyle(
                                color:
                                    Theme.of(context).brightness ==
                                        Brightness.dark
                                    ? Colors.white54
                                    : Colors.black45,
                              ),
                              border: InputBorder.none,
                              contentPadding: const EdgeInsets.symmetric(
                                horizontal: 20,
                                vertical: 14,
                              ),
                            ),
                            onSubmitted: (_) => _sendMessage(),
                          ),
                        ),
                        Padding(
                          padding: const EdgeInsets.only(right: 4.0),
                          child: Container(
                            decoration: BoxDecoration(
                              color: Colors.blueAccent,
                              shape: BoxShape.circle,
                            ),
                            child: IconButton(
                              icon: const Icon(
                                Icons.arrow_upward,
                                color: Colors.white,
                                size: 20,
                              ),
                              onPressed:
                                  context.watch<PatientProvider>().isResponding
                                  ? null
                                  : _sendMessage,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildObservationChips(ChatMessage msg) {
    final verdicts = _labelVerdicts.putIfAbsent(
      msg.id,
      () => {for (final label in msg.observationHints) label: null},
    );

    return Padding(
      padding: const EdgeInsets.only(top: 4, bottom: 2),
      child: Wrap(
        spacing: 6,
        runSpacing: 4,
        children: msg.observationHints.map((label) {
          final verdict = verdicts[label];
          final accepted = verdict == true;
          final dismissed = verdict == false;
          final acted = verdict != null;

          return InputChip(
            label: Text(
              label,
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w600,
                color: acted
                    ? (accepted ? Colors.green.shade900 : Colors.red.shade900)
                    : null,
                decoration: dismissed ? TextDecoration.lineThrough : null,
              ),
            ),
            avatar: acted
                ? Icon(
                    accepted ? Icons.check_circle : Icons.cancel,
                    size: 16,
                    color: accepted
                        ? Colors.green.shade700
                        : Colors.red.shade400,
                  )
                : const Icon(Icons.psychology_alt, size: 16),
            backgroundColor: acted
                ? (accepted ? Colors.green.shade50 : Colors.red.shade50)
                : null,
            deleteIcon: acted ? null : const Icon(Icons.close, size: 14),
            onDeleted: acted ? null : () => _setLabelVerdict(msg, label, false),
            onPressed: acted ? null : () => _setLabelVerdict(msg, label, true),
            tooltip: acted
                ? (accepted ? 'Accepted' : 'Dismissed')
                : 'Tap to accept, ✕ to dismiss',
            materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
            visualDensity: VisualDensity.compact,
          );
        }).toList(),
      ),
    );
  }

  void _setLabelVerdict(ChatMessage msg, String label, bool accepted) {
    final settings = context.read<SettingsProvider>();

    // Show consent dialog on first interaction if not yet shown
    if (!settings.consentDialogShown) {
      _showTelemetryConsentDialog(context, () {
        // After dialog is handled, apply the verdict
        _applyVerdict(msg, label, accepted);
      });
      return;
    }

    _applyVerdict(msg, label, accepted);
  }

  void _applyVerdict(ChatMessage msg, String label, bool accepted) {
    setState(() {
      _labelVerdicts.putIfAbsent(
        msg.id,
        () => {for (final l in msg.observationHints) l: null},
      )[label] = accepted;
    });

    // Check if all labels have been decided
    final verdicts = _labelVerdicts[msg.id]!;
    final allDecided = verdicts.values.every((v) => v != null);
    if (allDecided) {
      _queueTelemetryEvent(msg, verdicts.cast<String, bool>());
    }
  }

  void _queueTelemetryEvent(ChatMessage msg, Map<String, bool> verdicts) {
    final provider = context.read<PatientProvider>();
    final telemetry = context.read<TelemetryService>();

    // Find the user message that preceded this assistant response
    final messages = provider.messages;
    String transcript = '';
    final msgIndex = messages.indexWhere((m) => m.id == msg.id);
    if (msgIndex > 0) {
      for (int i = msgIndex - 1; i >= 0; i--) {
        if (messages[i].role == 'user') {
          transcript = messages[i].content;
          break;
        }
      }
    }

    telemetry.recordLabelVerdict(
      transcript: transcript,
      suggestedLabels: msg.observationHints,
      verdicts: verdicts,
      patientName: provider.selectedPatient?.name,
    );
  }

  void _showTelemetryConsentDialog(BuildContext context, VoidCallback onDone) {
    final settings = context.read<SettingsProvider>();
    settings.markConsentDialogShown();

    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Row(
            children: [
              Icon(Icons.volunteer_activism, color: Color(0xFF06B6D4)),
              SizedBox(width: 12),
              Expanded(
                child: Text(
                  'Help improve suggestions?',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
                ),
              ),
            ],
          ),
          content: const SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'When you accept or dismiss a suggested observation label, '
                  'we can use that feedback to improve future suggestions.\n',
                ),
                Text(
                  "What's collected:",
                  style: TextStyle(fontWeight: FontWeight.w700),
                ),
                Text(
                  '• Which labels were suggested and whether you kept them\n'
                  '• A de-identified version of the note text that triggered '
                  'the suggestion (room numbers, MRN-like digits, and patient '
                  'names are removed before anything leaves the device)\n',
                ),
                Text(
                  "What's NOT collected:",
                  style: TextStyle(fontWeight: FontWeight.w700),
                ),
                Text(
                  '• Raw patient data or chart records\n'
                  '• Any data that could auto-chart anything\n',
                ),
                Text(
                  'You can turn this off anytime in Settings, view queued '
                  'events, or clear them at any time.',
                  style: TextStyle(fontStyle: FontStyle.italic),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.pop(dialogContext);
                onDone();
              },
              child: const Text('No thanks'),
            ),
            FilledButton.icon(
              onPressed: () {
                settings.setTelemetrySharingEnabled(true);
                Navigator.pop(dialogContext);
                onDone();
              },
              icon: const Icon(Icons.check),
              label: const Text('Enable & help improve'),
            ),
          ],
        );
      },
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

  void _showMessageOptions(BuildContext context, ChatMessage msg) {
    final isUser = msg.role == 'user';
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (context) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (isUser)
                ListTile(
                  leading: const Icon(Icons.edit_outlined),
                  title: const Text('Edit message text'),
                  onTap: () {
                    Navigator.pop(context);
                    _editMessageText(context, msg);
                  },
                ),
              ListTile(
                leading: const Icon(Icons.delete_outline, color: Colors.red),
                title: const Text('Delete message', style: TextStyle(color: Colors.red)),
                onTap: () {
                  Navigator.pop(context);
                  context.read<PatientProvider>().deleteMessage(msg);
                },
              ),
            ],
          ),
        );
      },
    );
  }

  void _editMessageText(BuildContext context, ChatMessage msg) {
    final editController = TextEditingController(text: msg.content);
    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('Edit Message'),
          content: TextField(
            controller: editController,
            maxLines: 3,
            decoration: const InputDecoration(
              hintText: 'Edit your message...',
              border: OutlineInputBorder(),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () {
                final newText = editController.text.trim();
                if (newText.isNotEmpty) {
                  context.read<PatientProvider>().updateMessageText(msg, newText);
                }
                Navigator.pop(context);
              },
              child: const Text('Save'),
            ),
          ],
        );
      },
    );
  }
}
