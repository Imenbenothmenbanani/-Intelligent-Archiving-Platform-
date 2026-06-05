import { Routes } from '@angular/router';
import { ScannerPageComponent } from './scanner-page/scanner-page.component';
import { QueryPageComponent } from './query-page/query-page.component';

export const routes: Routes = [
  {
    path: '',
    component: ScannerPageComponent,
    title: 'Document Scanner'
  },
  {
    path: 'query',
    component: QueryPageComponent,
    title: 'Document Search'
  },
  {
    path: '**',
    redirectTo: ''
  }
];
