import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:provider/provider.dart';
import '../providers/patient_provider.dart';
import '../models/types.dart';

class ChatHistoryDrawer extends StatefulWidget {
  final VoidCallback onChatSelected;

  const ChatHistoryDrawer({super.key, required this.onChatSelected});

  @override
  State<ChatHistoryDrawer> createState() => _ChatHistoryDrawerState();
}

class _ChatHistoryDrawerState extends State<ChatHistoryDrawer>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;
  Map<String, List<Map<String, dynamic>>>? _memoryCache;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
    _tabController.addListener(_handleTabSelection);
  }

  void _handleTabSelection() {
    if (_tabController.index == 1 && _memoryCache == null) {
      _loadMemory();
    }
  }

  Future<void> _loadMemory() async {
    final provider = context.read<PatientProvider>();
    final memory = await provider.getPatientMemoryRaw();
    if (mounted) {
      setState(() {
        _memoryCache = memory;
      });
    }
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final provider = context.watch<PatientProvider>();

    return Align(
      alignment: Alignment.centerRight,
      child:
          Material(
            color: Colors.transparent,
            child: Container(
              width: MediaQuery.of(context).size.width > 600
                  ? 400
                  : MediaQuery.of(context).size.width * 0.85,
              height: double.infinity,
              decoration: BoxDecoration(
                color: isDark
                    ? const Color(0xFF1E293B).withValues(alpha: 0.85)
                    : Colors.white.withValues(alpha: 0.85),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.1),
                    blurRadius: 16,
                    offset: const Offset(-4, 0),
                  ),
                ],
                border: Border(
                  left: BorderSide(
                    color: isDark
                        ? Colors.white.withValues(alpha: 0.1)
                        : Colors.black.withValues(alpha: 0.05),
                  ),
                ),
              ),
              child: ClipRRect(
                child: BackdropFilter(
                  filter: ImageFilter.blur(sigmaX: 16, sigmaY: 16),
                  child: Column(
                    children: [
                      SafeArea(
                        bottom: false,
                        child: Padding(
                          padding: const EdgeInsets.all(16.0),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              const Text(
                                'Management',
                                style: TextStyle(
                                  fontSize: 20,
                                  fontWeight: FontWeight.bold,
                                  letterSpacing: -0.5,
                                ),
                              ),
                              IconButton(
                                icon: const Icon(Icons.close),
                                onPressed: () => Navigator.pop(context),
                              ),
                            ],
                          ),
                        ),
                      ),
                      TabBar(
                        controller: _tabController,
                        indicatorColor: Theme.of(context).colorScheme.primary,
                        tabs: const [
                          Tab(text: 'Chat History'),
                          Tab(text: 'AI Memory'),
                        ],
                      ),
                      Expanded(
                        child: TabBarView(
                          controller: _tabController,
                          children: [
                            _buildChatHistoryTab(provider),
                            _buildMemoryTab(),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ).animate().slideX(
            begin: 1.0,
            end: 0,
            curve: Curves.easeOutCubic,
            duration: 300.ms,
          ),
    );
  }

  Widget _buildChatHistoryTab(PatientProvider provider) {
    if (provider.chatSessions.isEmpty) {
      return const Center(child: Text('No chat history.'));
    }

    return ListView.separated(
      padding: const EdgeInsets.all(8),
      itemCount: provider.chatSessions.length,
      separatorBuilder: (_, _) => const Divider(height: 1),
      itemBuilder: (context, index) {
        final session = provider.chatSessions[index];
        final isSelected = session.id == provider.activeChatSession?.id;

        return Dismissible(
          key: Key(session.id),
          direction: DismissDirection.endToStart,
          background: Container(
            alignment: Alignment.centerRight,
            padding: const EdgeInsets.only(right: 20),
            color: Colors.redAccent,
            child: const Icon(Icons.delete, color: Colors.white),
          ),
          onDismissed: (_) {
            provider.deleteChatSession(session);
          },
          child: ListTile(
            leading: Icon(
              isSelected ? Icons.chat_bubble : Icons.chat_bubble_outline,
              color: isSelected ? Theme.of(context).colorScheme.primary : null,
            ),
            title: Text(
              session.title,
              style: TextStyle(
                fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
              ),
            ),
            subtitle: Text(
              '${session.createdAt.day}/${session.createdAt.month}/${session.createdAt.year}',
            ),
            selected: isSelected,
            onTap: () async {
              await provider.selectChatSession(session);
              widget.onChatSelected();
            },
            onLongPress: () {
              _renameChatSession(context, session);
            },
          ),
        );
      },
    );
  }

  Widget _buildMemoryTab() {
    if (_memoryCache == null) {
      return const Center(child: CircularProgressIndicator());
    }

    final notes = _memoryCache!['notes'] ?? [];
    final vitals = _memoryCache!['vitals'] ?? [];
    final meds = _memoryCache!['medications'] ?? [];

    if (notes.isEmpty && vitals.isEmpty && meds.isEmpty) {
      return const Center(
        child: Text('No context available for this patient.'),
      );
    }

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const Text(
          'The AI uses the following recent records as context:',
          style: TextStyle(
            fontStyle: FontStyle.italic,
            fontSize: 13,
            color: Colors.grey,
          ),
        ),
        const SizedBox(height: 16),
        const SizedBox(height: 16),
        _buildMemorySection('Recent Vitals', vitals, 'vitals'),
        const SizedBox(height: 16),
        _buildMemorySection('Recent Notes', notes, 'notes'),
        const SizedBox(height: 16),
        _buildMemorySection('Medications', meds, 'medications'),
      ],
    ).animate().fade(duration: 400.ms);
  }

  Widget _buildMemorySection(String title, List<Map<String, dynamic>> items, String type) {
    if (items.isEmpty) return const SizedBox.shrink();
    final provider = context.read<PatientProvider>();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
        ),
        const SizedBox(height: 8),
        ...items.map(
          (item) => GestureDetector(
            onLongPress: () {
              showDialog(
                context: context,
                builder: (context) => AlertDialog(
                  title: const Text('Delete Record?'),
                  content: const Text('Are you sure you want to delete this record from the patient\'s memory?'),
                  actions: [
                    TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
                    FilledButton(
                      style: FilledButton.styleFrom(backgroundColor: Colors.red),
                      onPressed: () async {
                        Navigator.pop(context);
                        if (type == 'vitals') await provider.deleteVital(item['id'].toString());
                        else if (type == 'medications') await provider.deleteMedication(item['id'].toString());
                        else if (type == 'notes') await provider.deleteNursingNote(item['id'].toString());
                        _loadMemory();
                      },
                      child: const Text('Delete'),
                    ),
                  ],
                ),
              );
            },
            child: Card(
              margin: const EdgeInsets.only(bottom: 8),
              child: Padding(
                padding: const EdgeInsets.all(8.0),
                child: Text(
                  item.entries.where((e) => e.key != 'id' && e.key != 'patient_id').map((e) => '${e.key}: ${e.value}').join(' | '),
                  style: const TextStyle(fontSize: 12),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  void _renameChatSession(BuildContext context, ChatSession session) {
    final controller = TextEditingController(text: session.title);
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Rename Chat'),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(labelText: 'Chat Title'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          FilledButton(
            onPressed: () {
              context.read<PatientProvider>().renameChatSession(session, controller.text);
              Navigator.pop(context);
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );
  }
}
