import 'dart:isolate';

void main() async {
  final uri = await Isolate.resolvePackageUri(Uri.parse('package:flutter_gemma/flutter_gemma.dart'));
  print(uri);
}
