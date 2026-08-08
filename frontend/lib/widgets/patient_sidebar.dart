import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
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
        if (patients.isEmpty) {
          return const Center(child: Text("No patients found"));
        }

        return Container(
          width: 250,
          color: Colors.grey[100],
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.all(16.0),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text(
                      "Patients",
                      style: TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    IconButton(
                      icon: const Icon(Icons.person_add),
                      onPressed: () => _showAddPatientDialog(context, provider),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: ListView.builder(
                  itemCount: patients.length,
                  itemBuilder: (context, index) {
                    final patient = patients[index];
                    final isSelected = provider.selectedPatient?.id == patient.id;

                    return ListTile(
                      title: Text(patient.name),
                      subtitle: Text("Room: ${patient.room} Bed: ${patient.bed}"),
                      selected: isSelected,
                      selectedTileColor: Colors.blue.withValues(alpha: 0.1),
                      onTap: () {
                        provider.selectPatient(patient);
                        if (Scaffold.of(context).isDrawerOpen) {
                          Navigator.pop(context); // Close drawer on mobile
                        }
                      },
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
                  "status": "Stable"
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
