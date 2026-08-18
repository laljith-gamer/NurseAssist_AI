import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../providers/patient_provider.dart';

class PatientSidebar extends StatelessWidget {
  const PatientSidebar({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<PatientProvider>(
      builder: (context, provider, child) {
        if (provider.isLoading) {
          return const Center(child: CircularProgressIndicator());
        }

        final patients = provider.patients;
        final isDark = Theme.of(context).brightness == Brightness.dark;

        return Container(
          width: 280,
          decoration: BoxDecoration(
            color: isDark
                ? const Color(0xFF0F172A).withValues(alpha: 0.8)
                : Colors.white.withValues(alpha: 0.7),
            border: Border(
              right: BorderSide(
                color: isDark
                    ? Colors.white.withValues(alpha: 0.05)
                    : Colors.black.withValues(alpha: 0.05),
              ),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.all(24.0),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      "Patients",
                      style: TextStyle(
                        fontSize: 22,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -0.5,
                        color: isDark ? Colors.white : const Color(0xFF0F172A),
                      ),
                    ),
                    Container(
                      decoration: BoxDecoration(
                        color: Theme.of(
                          context,
                        ).colorScheme.primary.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: IconButton(
                        icon: Icon(
                          Icons.person_add,
                          color: Theme.of(context).colorScheme.primary,
                        ),
                        onPressed: () =>
                            _showAddPatientDialog(context, provider),
                        tooltip: 'Admit Patient',
                      ),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: patients.isEmpty
                    ? const Center(child: Text("No patients found"))
                    : ListView.builder(
                        padding: const EdgeInsets.symmetric(horizontal: 16),
                        itemCount: patients.length,
                        itemBuilder: (context, index) {
                          final patient = patients[index];
                          final isSelected =
                              provider.selectedPatient?.id == patient.id;

                          return _AnimatedPatientListItem(
                                patient: patient,
                                isSelected: isSelected,
                                onTap: () {
                                  provider.selectPatient(patient);
                                  if (Scaffold.of(context).isDrawerOpen) {
                                    Navigator.pop(context);
                                  }
                                },
                              )
                              .animate(
                                delay: Duration(milliseconds: 50 * index),
                              )
                              .fadeIn(duration: 300.ms)
                              .slideX(
                                begin: -0.1,
                                end: 0,
                                duration: 300.ms,
                                curve: Curves.easeOut,
                              );
                        },
                      ),
              ),
            ],
          ),
        );
      },
    );
  }

  void _showAddPatientDialog(BuildContext context, PatientProvider provider) {
    final firstNameController = TextEditingController();
    final lastNameController = TextEditingController();
    final roomController = TextEditingController();

    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('Admit New Patient'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: firstNameController,
                  decoration: const InputDecoration(labelText: 'First Name'),
                ),
                TextField(
                  controller: lastNameController,
                  decoration: const InputDecoration(labelText: 'Last Name'),
                ),
                TextField(
                  controller: roomController,
                  decoration: const InputDecoration(labelText: 'Room Number'),
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
                final patientData = {
                  "first_name": firstNameController.text,
                  "last_name": lastNameController.text,
                  "age": 45,
                  "gender": "Unknown",
                  "room": roomController.text,
                  "mrn": "MRN-${DateTime.now().millisecondsSinceEpoch}",
                  "primary_diagnosis": "Pending",
                  "allergies": "None",
                  "status": "Stable",
                };

                final success = await provider.addPatient(patientData);
                if (success && context.mounted) {
                  Navigator.pop(context);
                }
              },
              child: const Text('Admit'),
            ),
          ],
        );
      },
    );
  }
}

class _AnimatedPatientListItem extends StatefulWidget {
  final dynamic patient;
  final bool isSelected;
  final VoidCallback onTap;

  const _AnimatedPatientListItem({
    required this.patient,
    required this.isSelected,
    required this.onTap,
  });

  @override
  State<_AnimatedPatientListItem> createState() =>
      _AnimatedPatientListItemState();
}

class _AnimatedPatientListItemState extends State<_AnimatedPatientListItem> {
  bool _isHovered = false;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return MouseRegion(
      onEnter: (_) => setState(() => _isHovered = true),
      onExit: (_) => setState(() => _isHovered = false),
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: widget.onTap,
        onLongPress: () => _showPatientOptionsDialog(context),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOutCubic,
          margin: const EdgeInsets.only(bottom: 8),
          transform: Matrix4.diagonal3Values(
            _isHovered ? 1.02 : 1.0,
            _isHovered ? 1.02 : 1.0,
            1.0,
          ),
          decoration: BoxDecoration(
            color: widget.isSelected
                ? Theme.of(
                    context,
                  ).colorScheme.primary.withValues(alpha: isDark ? 0.2 : 0.1)
                : (_isHovered
                      ? (isDark
                            ? Colors.white.withValues(alpha: 0.05)
                            : Colors.black.withValues(alpha: 0.03))
                      : Colors.transparent),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: widget.isSelected
                  ? Theme.of(context).colorScheme.primary.withValues(alpha: 0.5)
                  : Colors.transparent,
              width: 1.5,
            ),
          ),
          child: ListTile(
            contentPadding: const EdgeInsets.symmetric(
              horizontal: 16,
              vertical: 8,
            ),
            title: Text(
              widget.patient.name,
              style: TextStyle(
                fontWeight: widget.isSelected
                    ? FontWeight.bold
                    : FontWeight.w600,
                color: widget.isSelected
                    ? Theme.of(context).colorScheme.primary
                    : (isDark ? Colors.white : const Color(0xFF334155)),
              ),
            ),
            subtitle: Text(
              "Room: ${widget.patient.room} • Bed: ${widget.patient.bed}",
              style: TextStyle(
                fontSize: 12,
                color: isDark ? Colors.grey[400] : Colors.grey[600],
              ),
            ),
            leading: CircleAvatar(
              backgroundColor: widget.isSelected
                  ? Theme.of(context).colorScheme.primary
                  : (isDark
                        ? const Color(0xFF334155)
                        : const Color(0xFFE2E8F0)),
              foregroundColor: widget.isSelected
                  ? Colors.white
                  : (isDark ? Colors.white : const Color(0xFF475569)),
              child: Text(widget.patient.name[0].toUpperCase()),
            ),
          ),
        ),
      ),
    );
  }

  void _showPatientOptionsDialog(BuildContext context) {
    final provider = context.read<PatientProvider>();
    showModalBottomSheet(
      context: context,
      builder: (context) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ListTile(
                leading: const Icon(Icons.edit),
                title: const Text('Edit Patient Name'),
                onTap: () {
                  Navigator.pop(context);
                  _editPatientDialog(context, provider);
                },
              ),
              ListTile(
                leading: const Icon(Icons.delete, color: Colors.red),
                title: const Text('Discharge / Delete Patient', style: TextStyle(color: Colors.red)),
                onTap: () {
                  Navigator.pop(context);
                  _confirmDeletePatient(context, provider);
                },
              ),
            ],
          ),
        );
      },
    );
  }

  void _editPatientDialog(BuildContext context, PatientProvider provider) {
    final nameController = TextEditingController(text: widget.patient.name);
    final diagnosisController = TextEditingController(text: widget.patient.primaryDiagnosis);

    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('Edit Patient Info'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: nameController,
                decoration: const InputDecoration(labelText: 'Patient Name'),
              ),
              TextField(
                controller: diagnosisController,
                decoration: const InputDecoration(labelText: 'Primary Diagnosis / Notes'),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
            FilledButton(
              onPressed: () {
                provider.updatePatient(nameController.text, diagnosisController.text);
                Navigator.pop(context);
              },
              child: const Text('Save'),
            ),
          ],
        );
      },
    );
  }

  void _confirmDeletePatient(BuildContext context, PatientProvider provider) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete Patient?'),
        content: const Text('Are you sure you want to completely remove this patient and all of their chat history, vitals, and notes? This cannot be undone.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            onPressed: () {
              provider.deletePatient();
              Navigator.pop(context);
            },
            child: const Text('Delete'),
          ),
        ],
      ),
    );
  }
}
