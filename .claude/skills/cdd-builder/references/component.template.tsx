/**
 * VORLAGE fuer cdd-builder — eine React-Native-Komponente pro klassifiziertem
 * CDD-Bauteil. Ersetze Platzhalter durch die Werte aus deduplicated-components.json:
 *   <ComponentName>   = classification.componentName  (PascalCase)
 *   <canonicalCddId>  = canonicalCddId  (Anker im indizierten HTML)
 *   <category>        = atom | molecule | organism
 *
 * Regeln: kein <div>/<span>, kein className; jeder Text in <Text>; Styles via
 * StyleSheet.create; Unterschiede zwischen Instanzen werden zu Props.
 */

// ---------------------------------------------------------------------------
// BEISPIEL ATOM  (reactNative: "Pressable")  ->  cdd-id: <canonicalCddId>
// HTML-Quelle: <button class="btn btn-primary">…</button>  (occurrences: 7)
// ---------------------------------------------------------------------------
import { Pressable, StyleSheet, Text } from 'react-native';

export interface PrimaryButtonProps {
  /** Unterschied zwischen den 7 Instanzen -> Prop statt 7 Komponenten */
  label: string;
  onPress?: () => void;
}

export function PrimaryButton({ label, onPress }: PrimaryButtonProps) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={styles.primaryButton}>
      <Text style={styles.primaryButtonLabel}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  primaryButton: {
    backgroundColor: '#ede900',
    borderRadius: 9999,
    paddingVertical: 16,
    paddingHorizontal: 24,
    alignItems: 'center'
  },
  primaryButtonLabel: {
    color: '#1d1d00',
    fontSize: 16,
    fontWeight: '700'
  }
});

// ---------------------------------------------------------------------------
// BEISPIEL MOLEKUEL  (reactNative: "View")  ->  importiert seine dependsOn-Atome
// HTML-Quelle: <div class="field"><label/><input/></div>  (occurrences: 5)
// ---------------------------------------------------------------------------
// import { View, Text, TextInput, StyleSheet } from 'react-native';
//
// export interface FormFieldProps {           // Props = Instanz-Unterschiede
//   label: string;
//   placeholder?: string;
//   secureTextEntry?: boolean;                 // aus type="password"
// }
//
// export function FormField({ label, placeholder, secureTextEntry }: FormFieldProps) {
//   return (
//     <View style={styles.field}>
//       <Text style={styles.fieldLabel}>{label}</Text>
//       <TextInput style={styles.fieldInput} placeholder={placeholder}
//                  secureTextEntry={secureTextEntry} />
//     </View>
//   );
// }
//
// Ein ORGANISMUS (z.B. AuthForm) importiert seinerseits FormField + PrimaryButton
// und rendert sie — Dependency-First, jede Komponente genau einmal.
