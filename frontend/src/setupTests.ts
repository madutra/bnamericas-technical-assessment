import '@testing-library/jest-dom'
import { TextDecoder, TextEncoder } from 'node:util'

// React Router needs these and jsdom does not provide them.
Object.assign(globalThis, { TextEncoder, TextDecoder })
